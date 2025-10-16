from flask import Flask, jsonify, request, render_template
from datetime import datetime, timedelta
import jwt
from functools import wraps
from flasgger import Swagger
from flask_caching import Cache # Import Cache

app = Flask(__name__)
app.config['SECRET_KEY'] = 'a_very_secret_key_that_should_be_changed'

# --- CẤU HÌNH CACHE ---
# Cấu hình để sử dụng cache đơn giản, lưu trong bộ nhớ.
config = {
    "DEBUG": True,
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300  # Cache mặc định 5 phút
}
app.config.from_mapping(config)
cache = Cache(app) # Khởi tạo đối tượng cache


# --- CẤU HÌNH SWAGGER ---
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Library API V4 (Cacheable)", # Cập nhật tiêu đề
        "description": "API cho hệ thống thư viện, đã được tích hợp caching để tăng hiệu năng.",
        "version": "4.0.0" # Cập nhật phiên bản
    },
    "host": "127.0.0.1:5000",
    "basePath": "/",
    "schemes": ["http"],
    "securityDefinitions": {
        "APIKeyHeader": {
            "type": "apiKey",
            "name": "x-access-token",
            "in": "header",
            "description": "JWT Token"
        }
    }
}
swagger = Swagger(app, template=swagger_template)


# --- Dữ liệu mẫu (giữ nguyên) ---
users = [
    {'id': 1, 'username': 'user_one', 'password': 'password1'},
    {'id': 2, 'username': 'user_two', 'password': 'password2'}
]
books = [
    {'id': 1, 'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5},
    {'id': 2, 'title': 'Số Đỏ', 'author': 'Vũ Trọng Phụng', 'quantity': 3},
    {'id': 3, 'title': 'Dế Mèn Phiêu Lưu Ký', 'author': 'Tô Hoài', 'quantity': 10},
    {'id': 4, 'title': 'Nhà Giả Kim', 'author': 'Paulo Coelho', 'quantity': 8},
    {'id': 5, 'title': 'Đắc Nhân Tâm', 'author': 'Dale Carnegie', 'quantity': 15},
    {'id': 6, 'title': 'Harry Potter và Hòn Đá Phù Thủy', 'author': 'J.K. Rowling', 'quantity': 7},
    {'id': 7, 'title': 'Tắt Đèn', 'author': 'Ngô Tất Tố', 'quantity': 0}
]
borrow_records = []
next_borrow_id = 1

# --- Decorator (giữ nguyên) ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token: return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = next((u for u in users if u['id'] == data['user_id']), None)
            if not current_user: return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# === API Routes với tài liệu Swagger ===

@app.route('/api/login', methods=['POST'])
def login():
    """
    Đăng nhập và nhận JWT Token
    Sử dụng token này để xác thực cho các request khác.
    ---
    tags: [Authentication]
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Login
          required: [username, password]
          properties:
            username: {type: string, description: Tên đăng nhập, default: "user_one"}
            password: {type: string, description: Mật khẩu, default: "password1"}
    responses:
      200: {description: Đăng nhập thành công, trả về token.}
      401: {description: Sai thông tin đăng nhập.}
    """
    data = request.json
    user = next((u for u in users if u['username'] == data.get('username')), None)
    if not user or user['password'] != data.get('password'):
        return jsonify({'message': 'Could not verify, invalid credentials'}), 401
    token = jwt.encode({
        'user_id': user['id'],
        'username': user['username'],
        'exp': datetime.utcnow() + timedelta(minutes=60)
    }, app.config['SECRET_KEY'], algorithm="HS256")
    return jsonify({'token': token})


@app.route('/api/books', methods=['GET'])
@token_required
# Cache sẽ tự động hoạt động với các tham số query khác nhau
# Tức là /api/books?page=1 và /api/books?page=2 sẽ được cache riêng biệt
@cache.cached(timeout=60, query_string=True)
def get_all_books(current_user):
    """
    Lấy danh sách sách, hỗ trợ tìm kiếm và phân trang (ĐÃ ĐƯỢC CACHE)
    Kết quả được cache trong 60 giây. Các tham số tìm kiếm/phân trang khác nhau sẽ tạo cache riêng.
    ---
    tags: [Books]
    security:
      - APIKeyHeader: []
    # highlight-start
    # --- THÊM THAM SỐ VÀO SWAGGER ---
    parameters:
      - name: title
        in: query
        type: string
        required: false
        description: Tìm kiếm sách theo tiêu đề (không phân biệt hoa thường).
      - name: author
        in: query
        type: string
        required: false
        description: Lọc sách theo tên tác giả.
      - name: page
        in: query
        type: integer
        required: false
        default: 1
        description: Số trang muốn lấy.
      - name: limit
        in: query
        type: integer
        required: false
        default: 5
        description: Số lượng sách trên mỗi trang.
    # highlight-end
    responses:
      200:
        description: Danh sách các quyển sách.
      401:
        description: Token không hợp lệ hoặc bị thiếu.
    """
    print("LOG: Fetching books from data source (not cache)...")

    # --- Lấy các tham số từ query string ---
    title_query = request.args.get('title', type=str)
    author_query = request.args.get('author', type=str)
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 5, type=int)

    # --- Lọc dữ liệu (Filtering) ---
    filtered_books = list(books)  # Bắt đầu với toàn bộ danh sách

    if title_query:
        # Lọc theo tiêu đề, tìm kiếm chứa chuỗi và không phân biệt hoa thường
        filtered_books = [
            book for book in filtered_books
            if title_query.lower() in book['title'].lower()
        ]

    if author_query:
        # Lọc theo tác giả
        filtered_books = [
            book for book in filtered_books
            if author_query.lower() in book['author'].lower()
        ]

    # --- Phân trang (Pagination) ---
    total_items = len(filtered_books)
    start_index = (page - 1) * limit
    end_index = start_index + limit

    # Cắt danh sách để lấy đúng các mục cho trang hiện tại
    paginated_data = filtered_books[start_index:end_index]

    # Tính tổng số trang
    total_pages = (total_items + limit - 1) // limit

    # --- Trả về response JSON hoàn chỉnh ---
    return jsonify({
        'message': 'Books retrieved successfully',
        'data': paginated_data,
        'pagination': {
            'currentPage': page,
            'limit': limit,
            'totalItems': total_items,
            'totalPages': total_pages
        }
    })

@app.route('/api/borrow-records', methods=['GET'])
@token_required
def get_my_borrow_records(current_user):
    """
    Lấy lịch sử mượn sách của người dùng đã đăng nhập
    ---
    tags: [Borrowing]
    security:
      - APIKeyHeader: []
    responses:
      200: {description: Danh sách các phiếu mượn của bạn.}
      401: {description: Token không hợp lệ hoặc bị thiếu.}
    """
    my_records = [r for r in borrow_records if r['user_id'] == current_user['id']]
    return jsonify({'records': my_records})

@app.route('/api/borrow-records', methods=['POST'])
@token_required
def borrow_book(current_user):
    """
    Mượn một quyển sách mới
    Hành động này sẽ xóa cache của danh sách sách.
    ---
    tags: [Borrowing]
    security:
      - APIKeyHeader: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Borrow
          required: [book_id]
          properties:
            book_id: {type: integer, description: ID của sách muốn mượn.}
    responses:
      201: {description: Mượn sách thành công.}
      404: {description: Sách không tồn tại hoặc đã hết.}
    """
    global next_borrow_id
    data = request.json
    book_id = data.get('book_id')
    book = next((b for b in books if b['id'] == book_id), None)
    if not book or book['quantity'] <= 0:
        return jsonify({'error': 'Sách không hợp lệ hoặc đã hết'}), 404

    # XÓA CACHE: Vì số lượng sách thay đổi, cần xóa cache cũ
    cache.delete('view//api/books')
    print("LOG: Book list cache cleared due to borrowing.")

    book['quantity'] -= 1
    new_record = {'id': next_borrow_id, 'user_id': current_user['id'], 'username': current_user['username'], 'book_id': book_id, 'book_title': book['title'], 'borrow_date': datetime.utcnow().isoformat() + 'Z', 'returned': False}
    borrow_records.append(new_record)
    next_borrow_id += 1
    return jsonify({'message': f"User '{current_user['username']}' mượn sách '{book['title']}' thành công", 'record': new_record}), 201


@app.route('/api/borrow-records/<int:record_id>', methods=['PUT'])
@token_required
def return_book(current_user, record_id):
    """
    Trả một quyển sách đã mượn
    Hành động này sẽ xóa cache của danh sách sách.
    ---
    tags: [Borrowing]
    security:
      - APIKeyHeader: []
    parameters:
      - name: record_id
        in: path
        type: integer
        required: true
        description: ID của phiếu mượn cần trả.
    responses:
      200: {description: Trả sách thành công.}
      403: {description: Không có quyền trả phiếu mượn này.}
      404: {description: Không tìm thấy phiếu mượn.}
    """
    record = next((r for r in borrow_records if r['id'] == record_id), None)
    if not record: return jsonify({'error': 'Không tìm thấy phiếu mượn'}), 404
    if record['user_id'] != current_user['id']: return jsonify({'error': 'Bạn không có quyền trả phiếu mượn này'}), 403
    if record['returned']: return jsonify({'message': 'Sách này đã được trả từ trước'}), 200

    # XÓA CACHE: Vì số lượng sách thay đổi, cần xóa cache cũ
    cache.delete('view//api/books')
    print("LOG: Book list cache cleared due to returning.")

    book = next((b for b in books if b['id'] == record['book_id']), None)
    if book: book['quantity'] += 1
    record['returned'] = True
    record['return_date'] = datetime.utcnow().isoformat() + 'Z'
    return jsonify({'message': f"Trả sách '{book['title']}' thành công"}), 200

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    app.run(debug=True)
