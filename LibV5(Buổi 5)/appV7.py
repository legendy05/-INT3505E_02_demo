from flask import Flask, jsonify, request, render_template
from datetime import datetime, timedelta, timezone
import jwt
from functools import wraps
from flasgger import Swagger
from flask_bcrypt import Bcrypt
from flask_caching import Cache # Import Cache
import os
from dotenv import load_dotenv
import mongoengine as db
from mongoengine import connect
from mongoengine.errors import DoesNotExist, ValidationError

load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

bcrypt = Bcrypt(app)
# GỌI KẾT NỐI TRỰC TIẾP
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/library_db')
connect(db='library_db', host=mongo_uri)

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
        "title": "Library API V5", # Cập nhật tiêu đề
        "description": "API cho hệ thống thư viện.",
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


class User(db.Document):
    username = db.StringField(required=True, unique=True)
    password = db.StringField(required=True)
    roles = db.ListField(db.StringField(), default=['user'])
    meta = {'collection': 'users'}

    # Hàm băm mật khẩu
    def hash_password(self):
        self.password = bcrypt.generate_password_hash(self.password).decode('utf-8')

    # Hàm kiểm tra mật khẩu
    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def to_dict(self):
        return {
            'id': str(self.id),
            'username': self.username,
            'roles': self.roles
        }

class Book(db.Document):
    title = db.StringField(required=True)
    author = db.StringField(required=True)
    quantity = db.IntField(default=0)
    meta = {'collection': 'books'}

    def to_dict(self):
        return {
            'id': str(self.id),
            'title': self.title,
            'author': self.author,
            'quantity': self.quantity
        }

class BorrowRecord(db.Document):
    user_id = db.StringField(required=True)
    username = db.StringField(required=True)
    book_id = db.StringField(required=True)
    book_title = db.StringField(required=True)
    borrow_date = db.DateTimeField(default=datetime.utcnow)
    returned = db.BooleanField(default=False)
    return_date = db.DateTimeField(null=True)
    meta = {'collection': 'borrow_records'}

    def to_dict(self):
        return {
            'id': str(self.id),
            'user_id': self.user_id,
            'username': self.username,
            'book_id': self.book_id,
            'book_title': self.book_title,
            'borrow_date': self.borrow_date.isoformat() + 'Z',
            'returned': self.returned,
            'return_date': self.return_date.isoformat() + 'Z' if self.return_date else None
        }

# Decorator
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token: return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.objects(id = data['user_id']).first()
            if not current_user: return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)
    return decorated

# ---ENDPOINT ĐĂNG KÝ ---
@app.route('/api/register', methods=['POST'])
def register():
    """
    Đăng ký một người dùng mới
    Mật khẩu sẽ được tự động mã hóa.
    ---
    tags: [Authentication]
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Register
          required: [username, password]
          properties:
            username: {type: string, description: Tên đăng nhập mong muốn}
            password: {type: string, description: Mật khẩu}
    responses:
      201: {description: Đăng ký thành công.}
      400: {description: Tên đăng nhập đã tồn tại.}
    """
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Missing username or password'}), 400

    if User.objects(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists'}), 400

    new_user = User(
        username=data.get('username'),
        password=data.get('password') # Mật khẩu thô
    )
    new_user.hash_password() # Mã hóa mật khẩu
    new_user.save()

    return jsonify({'message': 'User registered successfully'}), 201

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
    user = User.objects(username=data.get('username')).first() # Tìm user trong DB
    if not user or not user.check_password(data.get('password')):
        return jsonify({'message': 'Could not verify, invalid credentials'}), 401
    token = jwt.encode({
        'user_id': str(user.id), # Chuyển ObjectId thành string
        'username': user.username,
        'roles': user.roles, # Thêm roles vào token
        'exp': datetime.now(timezone.utc) + timedelta(minutes=60)
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
    try:
        title_query = request.args.get('title', type=str)
        author_query = request.args.get('author', type=str)
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 5, type=int)

        query = Book.objects()
        if title_query:
            query = query.filter(title__icontains=title_query)
        if author_query:
            query = query.filter(author__icontains=author_query)

        # --- LOGIC PHÂN TRANG BẰNG MONGOENGINE NGUYÊN BẢN ---

        # 1. Đếm tổng số mục TRƯỚC KHI phân trang
        total_items = query.count()

        # 2. Tính tổng số trang
        total_pages = (total_items + limit - 1) // limit
        if page < 1: page = 1  # Đảm bảo trang không bị âm

        # 3. Tính toán vị trí bỏ qua (skip)
        skip_count = (page - 1) * limit

        # 4. Lấy dữ liệu của trang đó
        books_list = query.skip(skip_count).limit(limit)
        paginated_data = [book.to_dict() for book in books_list]
        # -----------------------------------------------

        # Đảm bảo hàm LUÔN LUÔN trả về response này
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

    except Exception as e:
        # Bắt các lỗi khác nếu có
        print(f"Error in get_all_books: {e}")
        return jsonify({'message': 'An internal error occurred', 'error': str(e)}), 500

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
    # Tìm các phiếu mượn của user (dùng ID từ token) trong DB
    records = BorrowRecord.objects(user_id=str(current_user.id))
    my_records_data = [r.to_dict() for r in records]
    return jsonify({'records': my_records_data})

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
            book_id: {type: string, description: ID của sách muốn mượn.}
    responses:
      201: {description: Mượn sách thành công.}
      404: {description: Sách không tồn tại hoặc đã hết.}
    """
    data = request.json
    book_id = data.get('book_id')

    try:
        book = Book.objects(id=book_id).first()
    except (DoesNotExist, ValidationError):
        return jsonify({'error': 'Book ID không hợp lệ'}), 400

    if not book or book.quantity <= 0:
        return jsonify({'error': 'Sách không tồn tại hoặc đã hết'}), 404

    # Giảm số lượng sách (atomic)
    book.update(dec__quantity=1)

    # XÓA CACHE (Giữ nguyên)
    cache.clear()
    print("LOG: Book list cache cleared due to borrowing.")

    # Tạo phiếu mượn mới trong DB
    new_record = BorrowRecord(
        user_id=str(current_user.id),
        username=current_user.username,
        book_id=str(book.id),
        book_title=book.title
    )
    new_record.save()

    return jsonify({
        'message': f"User '{current_user.username}' mượn sách '{book.title}' thành công",
        'record': new_record.to_dict()
    }), 201


@app.route('/api/borrow-records/<string:record_id>', methods=['PUT'])
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
        type: string
        required: true
        description: ID của phiếu mượn cần trả.
    responses:
      200: {description: Trả sách thành công.}
      403: {description: Không có quyền trả phiếu mượn này.}
      404: {description: Không tìm thấy phiếu mượn.}
    """
    try:
        record = BorrowRecord.objects(id=record_id).first()
    except (DoesNotExist, ValidationError):
        return jsonify({'error': 'Phiếu mượn không hợp lệ'}), 400

    if not record:
        return jsonify({'error': 'Không tìm thấy phiếu mượn'}), 404

        # Kiểm tra quyền sở hữu
    if record.user_id != str(current_user.id):
        return jsonify({'error': 'Bạn không có quyền trả phiếu mượn này'}), 403

    if record.returned:
        return jsonify({'message': 'Sách này đã được trả từ trước'}), 200

        # XÓA CACHE
    cache.clear()
    print("LOG: Book list cache cleared due to returning.")

    # Tăng lại số lượng sách (atomic)
    Book.objects(id=record.book_id).update(inc__quantity=1)

    # Cập nhật phiếu mượn là đã trả
    record.update(returned=True, return_date=datetime.utcnow())

    return jsonify({'message': f"Trả sách '{record.book_title}' thành công"}), 200

@app.route('/')
def index():
    return render_template('index2.html')

if __name__ == '__main__':
    # --- KHỐI THÊM DỮ LIỆU MẪU (SEEDING) ---
    print("Clearing old book data...")
    Book.objects.delete()  # Xóa sạch tất cả sách cũ để tránh trùng lặp

    print("Adding 20 sample books to database...")

    # Dữ liệu 20 cuốn sách
    sample_books_data = [
        {'title': 'Lão Hạc', 'author': 'Nam Cao', 'quantity': 5},
        {'title': 'Số Đỏ', 'author': 'Vũ Trọng Phụng', 'quantity': 3},
        {'title': 'Dế Mèn Phiêu Lưu Ký', 'author': 'Tô Hoài', 'quantity': 10},
        {'title': 'Nhà Giả Kim', 'author': 'Paulo Coelho', 'quantity': 8},
        {'title': 'Đắc Nhân Tâm', 'author': 'Dale Carnegie', 'quantity': 15},
        {'title': 'Harry Potter và Hòn Đá Phù Thủy', 'author': 'J.K. Rowling', 'quantity': 7},
        {'title': 'Tắt Đèn', 'author': 'Ngô Tất Tố', 'quantity': 2},
        {'title': 'Chiến Tranh và Hòa Bình', 'author': 'Leo Tolstoy', 'quantity': 4},
        {'title': 'Bố Già', 'author': 'Mario Puzo', 'quantity': 5},
        {'title': 'Những Người Khốn Khổ', 'author': 'Victor Hugo', 'quantity': 3},
        {'title': 'Tôi Thấy Hoa Vàng Trên Cỏ Xanh', 'author': 'Nguyễn Nhật Ánh', 'quantity': 12},
        {'title': 'Hai Số Phận', 'author': 'Jeffrey Archer', 'quantity': 6},
        {'title': 'Mắt Biếc', 'author': 'Nguyễn Nhật Ánh', 'quantity': 9},
        {'title': 'Giết Con Chim Nhại', 'author': 'Harper Lee', 'quantity': 4},
        {'title': 'Rừng Na Uy', 'author': 'Haruki Murakami', 'quantity': 7},
        {'title': '1984', 'author': 'George Orwell', 'quantity': 5},
        {'title': 'Ông Già và Biển Cả', 'author': 'Ernest Hemingway', 'quantity': 3},
        {'title': 'Hoàng Tử Bé', 'author': 'Antoine de Saint-Exupéry', 'quantity': 10},
        {'title': 'Trăm Năm Cô Đơn', 'author': 'Gabriel Garcia Marquez', 'quantity': 2},
        {'title': 'Chí Phèo', 'author': 'Nam Cao', 'quantity': 5}
    ]

    # Tạo các đối tượng Book từ data
    books_to_insert = [Book(**data) for data in sample_books_data]

    # Thêm hàng loạt vào DB (nhanh hơn là save() 20 lần)
    Book.objects.insert(books_to_insert)

    print(f"Successfully added {len(books_to_insert)} books.")
    # ----------------------------------------

    app.run(debug=True)
