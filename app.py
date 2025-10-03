from flask import Flask, render_template, request, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
import os

# Lấy đường dẫn tuyệt đối của thư mục chứa file app.py
basedir = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# Cấu hình đường dẫn cho database SQLite
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'library.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- Model: Định nghĩa cấu trúc của bảng Book trong database ---
class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    is_borrowed = db.Column(db.Boolean, default=False)

    def __repr__(self):
        return f'<Book {self.title}>'

# --- Routes: Định nghĩa các đường dẫn (URL) cho ứng dụng ---

# Route cho trang chủ: Hiển thị tất cả sách
@app.route('/')
def index():
    books = Book.query.all()
    return render_template('index.html', books=books)

# Route để thêm sách mới
@app.route('/add', methods=['POST'])
def add_book():
    title = request.form['title']
    author = request.form['author']
    new_book = Book(title=title, author=author, is_borrowed=False)
    db.session.add(new_book)
    db.session.commit()
    return redirect(url_for('index'))

# Route để mượn/trả sách
@app.route('/toggle/<int:book_id>')
def toggle_borrow_status(book_id):
    book = Book.query.get_or_404(book_id)
    book.is_borrowed = not book.is_borrowed  # Lật ngược trạng thái mượn
    db.session.commit()
    return redirect(url_for('index'))

# Route để xóa sách
@app.route('/delete/<int:book_id>')
def delete_book(book_id):
    book_to_delete = Book.query.get_or_404(book_id)
    db.session.delete(book_to_delete)
    db.session.commit()
    return redirect(url_for('index'))

# --- Chạy ứng dụng ---
if __name__ == '__main__':
    # Tạo database và các bảng nếu chúng chưa tồn tại
    with app.app_context():
        db.create_all()
    app.run(debug=True)