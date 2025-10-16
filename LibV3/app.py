from flask import Flask, jsonify, request, render_template
from datetime import datetime, timedelta
import jwt  # Thư viện PyJWT
from functools import wraps

app = Flask(__name__)
# Bắt buộc phải có SECRET_KEY để mã hóa JWT
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'

# --- Dữ liệu mẫu (thay cho database) ---
# Trong thực tế, bạn sẽ dùng Bcrypt để băm mật khẩu
users = [
    {'id': 1, 'username': 'user_one', 'password': 'password1'},
    {'id': 2, 'username': 'user_two', 'password': 'password2'}
]

# === CẬP NHẬT: Thêm nhiều sách hơn để kiểm thử ===
books = [
    {'id': 1, 'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5},
    {'id': 2, 'title': 'Số Đỏ', 'author': 'Vũ Trọng Phụng', 'quantity': 3},
    {'id': 3, 'title': 'Dế Mèn Phiêu Lưu Ký', 'author': 'Tô Hoài', 'quantity': 10},
    {'id': 4, 'title': 'Nhà Giả Kim', 'author': 'Paulo Coelho', 'quantity': 8},
    {'id': 5, 'title': 'Đắc Nhân Tâm', 'author': 'Dale Carnegie', 'quantity': 15},
    {'id': 6, 'title': 'Harry Potter và Hòn Đá Phù Thủy', 'author': 'J.K. Rowling', 'quantity': 7},
    # Thêm sách đã hết để kiểm tra logic
    {'id': 7, 'title': 'Tắt Đèn', 'author': 'Ngô Tất Tố', 'quantity': 0}
]
borrow_records = []
next_borrow_id = 1  # Biến để tạo ID tự tăng cho phiếu mượn


# === DECORATOR: BẢO VỆ CÁC ROUTE CẦN XÁC THỰC ===
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = next((u for u in users if u['id'] == data['user_id']), None)
            if not current_user:
                return jsonify({'message': 'User not found!'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired!'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Token is invalid!'}), 401

        return f(current_user, *args, **kwargs)

    return decorated


# === API XÁC THỰC (Không cần token) ===
@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Could not verify, missing username or password'}), 400

    username = data.get('username')
    password = data.get('password')
    user = next((u for u in users if u['username'] == username), None)

    if not user or user['password'] != password:
        return jsonify({'message': 'Could not verify, invalid credentials'}), 401

    token = jwt.encode({
        'user_id': user['id'],
        'username': user['username'],  # Thêm username vào payload
        'exp': datetime.utcnow() + timedelta(minutes=60)  # Tăng thời gian token
    }, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({'token': token})


# === API SÁCH (cần token để xem) ===
@app.route('/api/books', methods=['GET'])
@token_required
def get_all_books(current_user):
    return jsonify({'books': books})


# === API PHIẾU MƯỢN (Đã được bảo vệ) ===

# Lấy danh sách phiếu mượn của người dùng hiện tại
@app.route('/api/borrow-records', methods=['GET'])
@token_required
def get_my_borrow_records(current_user):
    my_records = [r for r in borrow_records if r['user_id'] == current_user['id']]
    return jsonify({'records': my_records})


# Tạo phiếu mượn mới
@app.route('/api/borrow-records', methods=['POST'])
@token_required
def borrow_book(current_user):
    global next_borrow_id
    data = request.json
    book_id = data.get('book_id')

    if not book_id:
        return jsonify({'error': 'Vui lòng cung cấp book_id'}), 400

    book = next((b for b in books if b['id'] == book_id), None)
    if not book or book['quantity'] <= 0:
        return jsonify({'error': 'Sách không hợp lệ hoặc đã hết'}), 404

    book['quantity'] -= 1

    new_record = {
        'id': next_borrow_id,
        'user_id': current_user['id'],
        'username': current_user['username'],
        'book_id': book_id,
        'book_title': book['title'],
        'borrow_date': datetime.utcnow().isoformat() + 'Z',
        'returned': False
    }
    borrow_records.append(new_record)
    next_borrow_id += 1  # Tăng ID cho lần mượn tiếp theo

    return jsonify({
        'message': f"User '{current_user['username']}' mượn sách '{book['title']}' thành công",
        'record': new_record
    }), 201


# Trả sách
@app.route('/api/borrow-records/<int:record_id>', methods=['PUT'])
@token_required
def return_book(current_user, record_id):
    record = next((r for r in borrow_records if r['id'] == record_id), None)

    if not record:
        return jsonify({'error': 'Không tìm thấy phiếu mượn'}), 404

    if record['user_id'] != current_user['id']:
        return jsonify({'error': 'Bạn không có quyền trả phiếu mượn này'}), 403

    if record['returned']:
        return jsonify({'message': 'Sách này đã được trả từ trước'}), 200

    # Cập nhật số lượng sách trong kho
    book = next((b for b in books if b['id'] == record['book_id']), None)
    if book:
        book['quantity'] += 1

    # Đánh dấu là đã trả
    record['returned'] = True
    record['return_date'] = datetime.utcnow().isoformat() + 'Z'

    return jsonify({'message': f"Trả sách '{book['title']}' thành công"}), 200


# === Route cho giao diện chính ===
@app.route('/')
def index():
    # Trả về file giao diện index.html
    return render_template('index.html')


if __name__ == '__main__':
    app.run(debug=True)

