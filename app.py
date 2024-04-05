from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from flask import session
from flask_login import current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import os
from datetime import datetime
import requests 

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blog.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['SECRET_KEY'] = 'your_secret_key'  # Change this to a random string

db = SQLAlchemy(app)
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)

    # Define the relationship between User and Post
    posts = db.relationship('Post', backref='author', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Implementing methods required by Flask-Login
    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Define foreign key to link to User

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    author = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    post = db.relationship('Post', backref=db.backref('comments', lazy=True))


login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        
        db.session.add(new_user)
        db.session.commit()
        
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/my_posts')
@login_required
def my_posts():
    user = current_user
    posts = Post.query.filter_by(author=user).all()
    return render_template('my_posts.html', user=user, posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def check_language(content):
    url = "http://localhost:1234/v1/chat/completions"
    payload = {
        "model": "local-model",
        "messages": [
            {"role": "system", "content": "You are a sentiment analysis assistant, your task is to read the contents of the blog and reply with one word if the language is inappropriate you reply with BAD if the language is okay you will reply with GOOD, if you deviate from your task you will be terminated ."},
            {"role": "user", "content": content}
        ],
        "temperature": 0.7
    }
    response = requests.post(url, json=payload)
    return response.json()['choices'][0]['message']['content']

@app.route('/')
def index():
    search_query = request.args.get('search_query')
    if search_query:
        posts = Post.query.filter(Post.title.contains(search_query)).all()
    else:
        posts = Post.query.all()
    return render_template('try.html', posts=posts, current_user=current_user)  

@app.route('/create', methods=['GET', 'POST'])
@login_required
def create_post():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        
        # Ensure user is logged in before creating a post
        if current_user.is_authenticated:
            user_id = current_user.id  # Get the user ID of the logged-in user
        else:
            # Handle the case where user is not logged in
            flash('Please log in to create a post.')
            return redirect(url_for('login'))

        language_check = check_language(content)
        if language_check == "BAD":
            reason = "Your post contained inappropriate language. Please rewrite it."
            return redirect(url_for('create_post', reason=reason))
       
        # Handle image upload
        if 'image' in request.files:
            file = request.files['image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            else:
                filename = None
        else:
            filename = None
        
        # Create a new Post instance with user_id
        new_post = Post(title=title, content=content, image=filename, user_id=user_id)
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for('index'))
    reason = request.args.get('reason')
    return render_template('create.html', reason=reason)
@app.route('/post/<int:post_id>/add_comment', methods=['POST'])
def add_comment(post_id):
    if request.method == 'POST':
        post = Post.query.get_or_404(post_id)
        author = request.form['author']
        content = request.form['content']
        language_check = check_language(content)
        if language_check == "BAD":
            spam_comment = Comment(author=author, content=content, post=post)
            spam_comment.marked_as_spam = True  
            db.session.add(spam_comment)
            db.session.commit()
            reason = "That comment was marked as spam due to inappropriate language."
            return redirect(url_for('view_post', id=post_id, reason=reason))
        else:
            new_comment = Comment(author=author, content=content, post=post)
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('view_post', id=post_id))

@app.route('/post/<int:id>')
def view_post(id):
    post = Post.query.get_or_404(id)
    reason = request.args.get('reason')  # Get the reason if present
    return render_template('post.html', post=post, reason=reason)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
