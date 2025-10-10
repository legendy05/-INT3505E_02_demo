from flask import Flask, jsonify, request, render_template
from datetime import datetime

app = Flask(__name__)

# --- Dữ liệu mẫu (thay cho database) ---
books = [
    {'id': 1, 'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5},
    {'id': 2, 'title': 'Số Đỏ', 'author': 'Vũ Trọng Phụng', 'quantity': 3},
]
# Giờ đây, mỗi phiếu mượn sẽ có ID riêng
borrow_records = [
    {'id': 101, 'book_id': 2, 'user_id': 1, 'borrow_date': '2025-10-09T10:00:00Z', 'is_returned': False}
]
next_book_id = 3
next_record_id = 102


# === API TÀI NGUYÊN SÁCH (/api/books) ===

@app.route('/api/books', methods=['GET'])
def get_books():
    """Lấy danh sách tất cả sách."""
    return jsonify(books)


@app.route('/api/books/<int:book_id>', methods=['GET'])
def get_book_by_id(book_id):
    """Lấy thông tin chi tiết của một cuốn sách."""
    book = next((b for b in books if b['id'] == book_id), None)
    if book:
        return jsonify(book)
    return jsonify({'error': 'Không tìm thấy sách'}), 404


@app.route('/api/books', methods=['POST'])
def create_book():
    """Tạo một sách mới."""
    global next_book_id
    data = request.json
    book = {
        'id': next_book_id,
        'title': data['title'],
        'author': data['author'],
        'quantity': data['quantity']
    }
    books.append(book)
    next_book_id += 1
    return jsonify(book), 201


# === API TÀI NGUYÊN PHIẾU MƯỢN (/api/borrow-records) ===

@app.route('/api/borrow-records', methods=['POST'])
def borrow_book():
    """Tạo một phiếu mượn mới (Hành động mượn sách)."""
    global next_record_id
    data = request.json
    book_id = data.get('book_id')
    user_id = data.get('user_id', 1)  # Mặc định user 1

    book = next((b for b in books if b['id'] == book_id), None)
    if not book:
        return jsonify({'error': 'Không tìm thấy sách'}), 404
    if book['quantity'] <= 0:
        return jsonify({'error': 'Sách đã hết'}), 400

    book['quantity'] -= 1

    new_record = {
        'id': next_record_id,
        'book_id': book_id,
        'user_id': user_id,
        'borrow_date': datetime.now().isoformat(),
        'is_returned': False
    }
    borrow_records.append(new_record)
    next_record_id += 1

    return jsonify({'message': 'Mượn sách thành công', 'record': new_record}), 201


@app.route('/api/borrow-records/<int:record_id>', methods=['DELETE'])
def return_book(record_id):
    """Xóa một phiếu mượn (Hành động trả sách)."""
    record = next((r for r in borrow_records if r['id'] == record_id and not r['is_returned']), None)

    if not record:
        return jsonify({'error': 'Không tìm thấy phiếu mượn hợp lệ'}), 404

    book = next((b for b in books if b['id'] == record['book_id']), None)
    if book:
        book['quantity'] += 1

    # Thay vì xóa, ta cập nhật trạng thái để giữ lại lịch sử
    record['is_returned'] = True
    record['return_date'] = datetime.now().isoformat()

    return jsonify({'message': 'Trả sách thành công'}), 200


# === Giao diện Client ===
@app.route('/')
def index():
    # Client (index.html) cũng cần được cập nhật để gọi đến các API mới này
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)