# app_v4.py
from flask import Flask, jsonify, request, render_template
from flask_caching import Cache  # Import thư viện Cache
import jwt
from datetime import datetime, timedelta, UTC
from functools import wraps

# --- CẤU HÌNH CACHE ---
# 'SimpleCache' lưu cache trong bộ nhớ của tiến trình server.
# Các loại khác bao gồm 'RedisCache', 'MemcachedCache' cho hệ thống lớn.
config = {
    "DEBUG": True,
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300  # Thời gian cache mặc định là 5 phút
}

app = Flask(__name__)
app.config.from_mapping(config)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'

cache = Cache(app)  # Khởi tạo đối tượng cache

# --- Dữ liệu và các hàm xác thực (giữ nguyên từ LibV3) ---
users = [{'id': 1, 'username': 'user_one', 'password': 'password1'}]
books = [{'id': 1, 'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5}]
borrow_records = []
next_book_id = 2



def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token: return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = next((u for u in users if u['id'] == data['user_id']), None)
        except:
            return jsonify({'message': 'Token is invalid!'}), 401
        return f(current_user, *args, **kwargs)

    return decorated


# === API TÀI NGUYÊN SÁCH (/api/books) ===

@app.route('/api/books', methods=['GET'])
@cache.cached(timeout=60)  # <-- ÁP DỤNG CACHE!
def get_books():
    """
    Lấy danh sách tất cả sách.
    Kết quả của hàm này sẽ được cache trong 60 giây.
    """
    print("--- Đang chạy logic để lấy sách từ 'database'... ---")  # Thêm để debug
    return jsonify(books)


@app.route('/api/books', methods=['POST'])
@token_required
def create_book(current_user):
    """
    Tạo một sách mới và XÓA CACHE CŨ.
    """
    global next_book_id
    data = request.json
    book = {
        'id': next_book_id,
        'title': data['title'],
        'author': data['author'],
        'quantity': int(data['quantity'])
    }
    books.append(book)
    next_book_id += 1

    # QUAN TRỌNG: Xóa cache của danh sách sách vì dữ liệu đã thay đổi.
    cache.delete('view//api/books')

    return jsonify(book), 201


# --- Các API và Route khác giữ nguyên như LibV3 ---
@app.route('/api/login', methods=['POST'])
def login():
    # ... Giữ nguyên logic login ...
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return jsonify({'message': 'Could not verify'}), 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}
    user = next((u for u in users if u['username'] == auth.username and u['password'] == auth.password), None)
    if not user:
        return jsonify({'message': 'Could not verify'}), 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}
    token = jwt.encode({'user_id': user['id'], 'exp': datetime.now(UTC) + timedelta(minutes=30)}, app.config['SECRET_KEY'], algorithm="HS256")
    return jsonify({'token': token})


# ... (Thêm các route còn lại của LibV3 vào đây)

@app.route('/')
def index():
    return render_template('index.html')


# Dán đoạn mã này vào file app_v4.py của bạn

# === API TÀI NGUYÊN PHIẾU MƯỢN (/api/borrow-records) ===

@app.route('/api/borrow-records', methods=['GET'])
def get_borrow_records():
    """
    Lấy danh sách các phiếu mượn.
    Hàm này giờ sẽ tạo một danh sách mới để gửi đi, an toàn hơn.
    """
    records_with_titles = []
    for record in borrow_records:
        book = next((b for b in books if b['id'] == record['book_id']), None)

        # Tạo một bản sao của phiếu mượn và thêm tựa sách vào
        record_copy = record.copy()
        record_copy['book_title'] = book['title'] if book else "Sách không rõ"
        records_with_titles.append(record_copy)

    return jsonify(records_with_titles)


@app.route('/api/borrow-records', methods=['POST'])
@token_required
def borrow_book(current_user):
    # ... (logic kiểm tra sách và số lượng giữ nguyên) ...
    data = request.json
    book_id = data.get('book_id')
    book = next((b for b in books if b['id'] == book_id), None)
    if not book or book['quantity'] <= 0:
        return jsonify({'error': 'Sách không hợp lệ hoặc đã hết'}), 400

    book['quantity'] -= 1

    # ... (logic tạo phiếu mượn giữ nguyên) ...

    # QUAN TRỌNG: Thêm dòng này để xóa cache cũ
    cache.delete('view//api/books')

    # ... (phần còn lại của hàm) ...
    return jsonify({'message': f"User {current_user['username']} mượn sách thành công"}), 201


# Trong file app_v4.py

@app.route('/api/borrow-records/<int:record_id>', methods=['DELETE'])
@token_required
def return_book(current_user, record_id):
    # ... (logic tìm phiếu mượn giữ nguyên) ...
    record = next((r for r in borrow_records if r['id'] == record_id and not r['is_returned']), None)
    if not record or record['user_id'] != current_user['id']:
        return jsonify({'error': 'Không tìm thấy phiếu mượn hoặc bạn không có quyền trả phiếu này'}), 403

    book = next((b for b in books if b['id'] == record['book_id']), None)
    if book:
        book['quantity'] += 1

    record['is_returned'] = True
    record['return_date'] = datetime.now().isoformat()

    # QUAN TRỌNG: Thêm dòng này để xóa cache cũ
    cache.delete('view//api/books')

    return jsonify({'message': 'Trả sách thành công'}), 200


if __name__ == '__main__':
    app.run(debug=True)