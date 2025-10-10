# app_v3.py
from flask import Flask, jsonify, request, render_template
from datetime import datetime, timedelta
import jwt  # Thư viện JWT
from functools import wraps  # Để tạo decorator

app = Flask(__name__)
# Bắt buộc phải có SECRET_KEY để mã hóa JWT
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'

# --- Dữ liệu mẫu (thay cho database) ---
# Trong thực tế, bạn sẽ dùng Bcrypt để băm mật khẩu
users = [
    {'id': 1, 'username': 'user_one', 'password': 'password1'},
    {'id': 2, 'username': 'user_two', 'password': 'password2'}
]
books = [{'id': 1, 'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5}]
borrow_records = []


# ... (dữ liệu khác giữ nguyên)

# === DECORATOR: BẢO VỆ CÁC ROUTE CẦN XÁC THỰC ===
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        # Token sẽ được gửi trong header 'x-access-token'
        if 'x-access-token' in request.headers:
            token = request.headers['x-access-token']

        if not token:
            return jsonify({'message': 'Token is missing!'}), 401

        try:
            # Giải mã token để lấy thông tin user
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = next((u for u in users if u['id'] == data['user_id']), None)
        except:
            return jsonify({'message': 'Token is invalid!'}), 401

        # Truyền thông tin user đã được xác thực vào hàm xử lý route
        return f(current_user, *args, **kwargs)

    return decorated


# === API XÁC THỰC (Không cần token) ===
@app.route('/api/login', methods=['POST'])
def login():
    auth = request.authorization
    if not auth or not auth.username or not auth.password:
        return jsonify({'message': 'Could not verify'}), 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    user = next((u for u in users if u['username'] == auth.username), None)

    if not user or user['password'] != auth.password:
        return jsonify({'message': 'Could not verify'}), 401, {'WWW-Authenticate': 'Basic realm="Login required!"'}

    # Tạo token có thời hạn 30 phút
    token = jwt.encode({
        'user_id': user['id'],
        'exp': datetime.utcnow() + timedelta(minutes=30)
    }, app.config['SECRET_KEY'], algorithm="HS256")

    return jsonify({'token': token})


# === API PHIẾU MƯỢN (Đã được bảo vệ) ===
@app.route('/api/borrow-records', methods=['POST'])
@token_required  # Áp dụng decorator bảo vệ
def borrow_book(current_user):  # `current_user` được truyền từ decorator
    # ... (code tìm sách, kiểm tra số lượng giữ nguyên) ...
    data = request.json
    book_id = data.get('book_id')
    book = next((b for b in books if b['id'] == book_id), None)
    if not book or book['quantity'] <= 0:
        return jsonify({'error': 'Sách không hợp lệ hoặc đã hết'}), 400

    book['quantity'] -= 1

    new_record = {
        # Lấy user_id từ `current_user` đã được xác thực, không phải từ request body
        'user_id': current_user['id'],
        'book_id': book_id,
        # ... (các trường khác giữ nguyên)
    }
    borrow_records.append(new_record)

    return jsonify({'message': f"User {current_user['username']} mượn sách thành công"}), 201


# --- Các route khác (`/api/books`, `/`) có thể giữ nguyên ---
# Bạn cũng có thể áp dụng @token_required cho route trả sách
@app.route('/api/borrow-records/<int:record_id>', methods=['DELETE'])
@token_required
def return_book(current_user, record_id):
    record = next((r for r in borrow_records if r['id'] == record_id), None)
    # Thêm bước kiểm tra xem người trả có phải là người đã mượn không
    if not record or record['user_id'] != current_user['id']:
        return jsonify({'error': 'Không tìm thấy phiếu mượn hoặc bạn không có quyền trả phiếu này'}), 403

    # ... (logic trả sách giữ nguyên)
    return jsonify({'message': 'Trả sách thành công'}), 200


# ... (thêm các route còn lại của bạn)
@app.route('/')
def index():
    return render_template('index.html')  # Cần cập nhật index.html để có form login


if __name__ == '__main__':
    app.run(debug=True)