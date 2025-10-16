from flask import Flask, jsonify, request, render_template
from datetime import datetime

app = Flask(__name__)

# Dữ liệu mẫu (thay cho database)
books = [
    {'id': 1, 'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5},
    {'id': 2, 'title': 'Số Đỏ', 'author': 'Vũ Trọng Phụng', 'quantity': 3},
    {'id': 3, 'title': 'Dế Mèn Phiêu Lưu Ký', 'author': 'Tô Hoài', 'quantity': 0}
]
borrow_records = []
next_book_id = 4


# --- API Quản lý Sách ---

# API lấy danh sách tất cả sách
@app.route('/api/books', methods=['GET'])
def get_books():
    return jsonify(books)


# API thêm một sách mới
@app.route('/api/books', methods=['POST'])
def add_book():
    global next_book_id
    new_book_data = request.json
    book = {
        'id': next_book_id,
        'title': new_book_data['title'],
        'author': new_book_data['author'],
        'quantity': new_book_data['quantity']
    }
    books.append(book)
    next_book_id += 1
    return jsonify(book), 201


# --- API Mượn - Trả Sách ---

# API mượn sách
@app.route('/api/borrow', methods=['POST'])
def borrow_book():
    data = request.json
    book_id = data['book_id']

    book = next((b for b in books if b['id'] == book_id), None)

    if not book:
        return jsonify({'error': 'Không tìm thấy sách'}), 404

    if book['quantity'] <= 0:
        return jsonify({'error': 'Sách đã hết'}), 400

    book['quantity'] -= 1
    record = {
        'book_id': book_id,
        'book_title': book['title'],
        'borrow_date': datetime.now().isoformat()
    }
    borrow_records.append(record)

    return jsonify({'message': f"Mượn sách '{book['title']}' thành công", 'book': book})


# API trả sách
@app.route('/api/return', methods=['POST'])
def return_book():
    data = request.json
    book_id = data['book_id']

    book = next((b for b in books if b['id'] == book_id), None)

    if not book:
        return jsonify({'error': 'Không tìm thấy sách'}), 404

    book['quantity'] += 1
    # (Trong một hệ thống thực tế, bạn cần xóa bản ghi mượn sách khỏi `borrow_records`)

    return jsonify({'message': f"Trả sách '{book['title']}' thành công", 'book': book})


# Route để phục vụ giao diện Client
@app.route('/')
def index():
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)