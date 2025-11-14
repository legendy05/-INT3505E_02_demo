from flask import Flask, jsonify, request, render_template, Blueprint
from datetime import datetime, timedelta, timezone
import jwt
from functools import wraps
from flasgger import Swagger
from flask_bcrypt import Bcrypt
from flask_caching import Cache
import os
from dotenv import load_dotenv
import mongoengine as db
from mongoengine import connect
from mongoengine.errors import DoesNotExist, ValidationError

# ======================================================================
# --- SECTION 2: APP INITIALIZATION & CONFIG (Khởi tạo) ---
# ======================================================================
load_dotenv()
app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY')

# Khởi tạo Bcrypt
bcrypt = Bcrypt(app)

# Kết nối MongoDB
mongo_uri = os.getenv('MONGO_URI', 'mongodb://localhost:27017/library_db')
connect(db='library_db', host=mongo_uri)

# Cấu hình Cache
config = {
    "DEBUG": True,
    "CACHE_TYPE": "SimpleCache",
    "CACHE_DEFAULT_TIMEOUT": 300
}
app.config.from_mapping(config)
cache = Cache(app)

# Cấu hình Swagger (Cập nhật cho V1 & V2)
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Library API (V1 & V2)",
        "description": "API cho hệ thống thư viện. V1 (deprecated) và V2 (hiện hành).",
        "version": "2.0.0"
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


# ======================================================================
# --- SECTION 3: DATABASE MODELS (Mô hình dữ liệu) ---
# (Giữ nguyên từ V7)
# ======================================================================
class User(db.Document):
    username = db.StringField(required=True, unique=True)
    password = db.StringField(required=True)
    roles = db.ListField(db.StringField(), default=['user'])
    meta = {'collection': 'users'}

    def hash_password(self):
        self.password = bcrypt.generate_password_hash(self.password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password, password)

    def to_dict(self):
        return {'id': str(self.id), 'username': self.username, 'roles': self.roles}


class Book(db.Document):
    title = db.StringField(required=True)
    author = db.StringField(required=True)
    quantity = db.IntField(default=0)
    meta = {'collection': 'books'}

    def to_dict(self):
        return {'id': str(self.id), 'title': self.title, 'author': self.author, 'quantity': self.quantity}


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


# ======================================================================
# --- SECTION 4: DECORATORS (Hàm hỗ trợ) ---
# (Giữ nguyên từ V7)
# ======================================================================
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('x-access-token')
        if not token: return jsonify({'message': 'Token is missing!'}), 401
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=["HS256"])
            current_user = User.objects(id=data['user_id']).first()
            if not current_user: return jsonify({'message': 'User not found!'}), 401
        except Exception as e:
            return jsonify({'message': 'Token is invalid!', 'error': str(e)}), 401
        return f(current_user, *args, **kwargs)

    return decorated


# ======================================================================
# --- SECTION 5: API V1 BLUEPRINT (Bản cũ, DEPRECATED) ---
# ======================================================================
v1_bp = Blueprint('v1_api', __name__, url_prefix='/api/v1')


# --- Hook: Tự động thêm header DEPRECATION cho MỌI response V1 ---
@v1_bp.after_request
def add_deprecation_warning(response):
    response.headers[
        'Warning'] = '299 - "This API version (v1) is deprecated and will be sunset on 2026-06-01. Please migrate to v2."'
    return response


@v1_bp.route('/register', methods=['POST'])
def register_v1():
    """
    Đăng ký user (V1)
    ---
    tags: [Authentication V1]
    parameters:
      - name: body
        in: body
        required: true
        schema: { $ref: "#/definitions/Register" }
    responses:
      201: {description: Đăng ký thành công.}
      400: {description: Tên đăng nhập đã tồn tại.}
    """
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Missing username or password'}), 400
    if User.objects(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists'}), 400
    new_user = User(username=data.get('username'), password=data.get('password'))
    new_user.hash_password()
    new_user.save()
    return jsonify({'message': 'User registered successfully'}), 201


@v1_bp.route('/login', methods=['POST'])
def login_v1():
    """
    Đăng nhập (V1)
    ---
    tags: [Authentication V1]
    parameters:
      - name: body
        in: body
        required: true
        schema: { $ref: "#/definitions/Login" }
    responses:
      200: {description: Đăng nhập thành công.}
      401: {description: Sai thông tin.}
    """
    data = request.json
    user = User.objects(username=data.get('username')).first()
    if not user or not user.check_password(data.get('password')):
        return jsonify({'message': 'Could not verify, invalid credentials'}), 401
    token = jwt.encode({
        'user_id': str(user.id),
        'username': user.username,
        'roles': user.roles,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=60)
    }, app.config['SECRET_KEY'], algorithm="HS256")
    return jsonify({'token': token})


@v1_bp.route('/books', methods=['GET'])
@token_required
@cache.cached(timeout=60, query_string=True)
def get_all_books_v1(current_user):
    """
    Lấy danh sách sách (V1 - DEPRECATED)
    Phiên bản này đã cũ và sẽ bị ngừng hỗ trợ.
    ---
    tags: [Books V1]
    security:
      - APIKeyHeader: []
    parameters:
      - name: title
        in: query
        type: string
        description: Tìm theo tiêu đề.
      - name: author
        in: query
        type: string
        description: Lọc theo tác giả.
      - name: page
        in: query
        type: integer
        default: 1
      - name: limit
        in: query
        type: integer
        default: 5
    responses:
      200: {description: Danh sách sách (Cấu trúc V1).}
    """
    print("LOG: V1 - Fetching books from data source (not cache)...")
    try:
        title_query = request.args.get('title', type=str)
        author_query = request.args.get('author', type=str)
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 5, type=int)

        query = Book.objects()
        if title_query: query = query.filter(title__icontains=title_query)
        if author_query: query = query.filter(author__icontains=author_query)

        total_items = query.count()
        total_pages = (total_items + limit - 1) // limit
        if page < 1: page = 1
        skip_count = (page - 1) * limit
        books_list = query.skip(skip_count).limit(limit)
        paginated_data = [book.to_dict() for book in books_list]

        # --- Cấu trúc Response V1 (Cũ) ---
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
        return jsonify({'message': 'An internal error occurred', 'error': str(e)}), 500


@v1_bp.route('/borrow-records', methods=['GET'])
@token_required
def get_my_borrow_records_v1(current_user):
    """
    Lấy lịch sử mượn (V1)
    ---
    tags: [Borrowing V1]
    security:
      - APIKeyHeader: []
    responses:
      200: {description: Danh sách phiếu mượn.}
    """
    records = BorrowRecord.objects(user_id=str(current_user.id))
    my_records_data = [r.to_dict() for r in records]
    return jsonify({'records': my_records_data})


@v1_bp.route('/borrow-records', methods=['POST'])
@token_required
def borrow_book_v1(current_user):
    """
    Mượn sách (V1)
    ---
    tags: [Borrowing V1]
    security:
      - APIKeyHeader: []
    parameters:
      - name: body
        in: body
        required: true
        schema: { $ref: "#/definitions/Borrow" }
    responses:
      201: {description: Mượn thành công.}
      404: {description: Sách không tồn tại/đã hết.}
    """
    data = request.json
    book_id = data.get('book_id')
    try:
        book = Book.objects(id=book_id).first()
    except (DoesNotExist, ValidationError):
        return jsonify({'error': 'Book ID không hợp lệ'}), 400
    if not book or book.quantity <= 0:
        return jsonify({'error': 'Sách không tồn tại hoặc đã hết'}), 404
    book.update(dec__quantity=1)
    cache.clear()
    print("LOG: V1 Cache cleared.")
    new_record = BorrowRecord(user_id=str(current_user.id), username=current_user.username, book_id=str(book.id),
                              book_title=book.title)
    new_record.save()
    return jsonify({'message': f"Mượn sách '{book.title}' thành công", 'record': new_record.to_dict()}), 201


@v1_bp.route('/borrow-records/<string:record_id>', methods=['PUT'])
@token_required
def return_book_v1(current_user, record_id):
    """
    Trả sách (V1)
    ---
    tags: [Borrowing V1]
    security:
      - APIKeyHeader: []
    parameters:
      - name: record_id
        in: path
        type: string
        required: true
    responses:
      200: {description: Trả sách thành công.}
      403: {description: Không có quyền.}
      404: {description: Không tìm thấy phiếu.}
    """
    try:
        record = BorrowRecord.objects(id=record_id).first()
    except (DoesNotExist, ValidationError):
        return jsonify({'error': 'Phiếu mượn không hợp lệ'}), 400
    if not record: return jsonify({'error': 'Không tìm thấy phiếu mượn'}), 404
    if record.user_id != str(current_user.id): return jsonify({'error': 'Không có quyền trả phiếu này'}), 403
    if record.returned: return jsonify({'message': 'Sách này đã được trả từ trước'}), 200
    cache.clear()
    print("LOG: V1 Cache cleared.")
    Book.objects(id=record.book_id).update(inc__quantity=1)
    record.update(returned=True, return_date=datetime.utcnow())
    return jsonify({'message': f"Trả sách '{record.book_title}' thành công"}), 200


# ======================================================================
# --- SECTION 6: API V2 BLUEPRINT (Bản mới, HIỆN HÀNH) ---
# ======================================================================
v2_bp = Blueprint('v2_api', __name__, url_prefix='/api/v2')


# V2 không cần hook `after_request`

@v2_bp.route('/register', methods=['POST'])
def register_v2():
    """
    Đăng ký user (V2)
    ---
    tags: [Authentication V2]
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Register  # Tái sử dụng schema từ Swagger
          required: [username, password]
          properties:
            username: {type: string}
            password: {type: string}
    responses:
      201: {description: Đăng ký thành công.}
      400: {description: Tên đăng nhập đã tồn tại.}
    """
    # Logic không đổi so với V1
    data = request.json
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'message': 'Missing username or password'}), 400
    if User.objects(username=data.get('username')).first():
        return jsonify({'message': 'Username already exists'}), 400
    new_user = User(username=data.get('username'), password=data.get('password'))
    new_user.hash_password()
    new_user.save()
    return jsonify({'message': 'User registered successfully'}), 201


@v2_bp.route('/login', methods=['POST'])
def login_v2():
    """
    Đăng nhập (V2)
    ---
    tags: [Authentication V2]
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Login # Tái sử dụng schema
          required: [username, password]
          properties:
            username: {type: string}
            password: {type: string}
    responses:
      200: {description: Đăng nhập thành công.}
      401: {description: Sai thông tin.}
    """
    # Logic không đổi so với V1
    data = request.json
    user = User.objects(username=data.get('username')).first()
    if not user or not user.check_password(data.get('password')):
        return jsonify({'message': 'Could not verify, invalid credentials'}), 401
    token = jwt.encode({
        'user_id': str(user.id),
        'username': user.username,
        'roles': user.roles,
        'exp': datetime.now(timezone.utc) + timedelta(minutes=60)
    }, app.config['SECRET_KEY'], algorithm="HS256")
    return jsonify({'token': token})


@v2_bp.route('/books', methods=['GET'])
@token_required
@cache.cached(timeout=60, query_string=True)
def get_all_books_v2(current_user):
    """
    Lấy danh sách sách (V2 - Hiện hành)
    Sử dụng cấu trúc response mới với { data: [], meta: {...} }.
    ---
    tags: [Books V2]
    security:
      - APIKeyHeader: []
    parameters:
      - name: title
        in: query
        type: string
        description: Tìm theo tiêu đề.
      - name: author
        in: query
        type: string
        description: Lọc theo tác giả.
      - name: page
        in: query
        type: integer
        default: 1
      - name: limit
        in: query
        type: integer
        default: 5
    responses:
      200: {description: Danh sách sách (Cấu trúc V2).}
    """
    print("LOG: V2 - Fetching books from data source (not cache)...")
    try:
        # Logic lấy data y hệt V1
        title_query = request.args.get('title', type=str)
        author_query = request.args.get('author', type=str)
        page = request.args.get('page', 1, type=int)
        limit = request.args.get('limit', 5, type=int)

        query = Book.objects()
        if title_query: query = query.filter(title__icontains=title_query)
        if author_query: query = query.filter(author__icontains=author_query)

        total_items = query.count()
        total_pages = (total_items + limit - 1) // limit
        if page < 1: page = 1
        skip_count = (page - 1) * limit
        books_list = query.skip(skip_count).limit(limit)
        paginated_data = [book.to_dict() for book in books_list]

        # --- *** BREAKING CHANGE *** ---
        # Cấu trúc Response V2 (Mới)
        return jsonify({
            'data': paginated_data,
            'meta': {
                'message': 'Books retrieved successfully',
                'pagination': {
                    'currentPage': page,
                    'limit': limit,
                    'totalItems': total_items,
                    'totalPages': total_pages
                }
            }
        })
        # ---------------------------------

    except Exception as e:
        return jsonify({'message': 'An internal error occurred', 'error': str(e)}), 500


@v2_bp.route('/borrow-records', methods=['GET'])
@token_required
def get_my_borrow_records_v2(current_user):
    """
    Lấy lịch sử mượn (V2)
    ---
    tags: [Borrowing V2]
    security:
      - APIKeyHeader: []
    responses:
      200: {description: Danh sách phiếu mượn.}
    """
    # Logic không đổi so với V1
    records = BorrowRecord.objects(user_id=str(current_user.id))
    my_records_data = [r.to_dict() for r in records]
    return jsonify({'records': my_records_data})


@v2_bp.route('/borrow-records', methods=['POST'])
@token_required
def borrow_book_v2(current_user):
    """
    Mượn sách (V2)
    ---
    tags: [Borrowing V2]
    security:
      - APIKeyHeader: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          id: Borrow # Tái sử dụng schema
          required: [book_id]
          properties:
            book_id: {type: string}
    responses:
      201: {description: Mượn thành công.}
      404: {description: Sách không tồn tại/đã hết.}
    """
    # Logic không đổi so với V1
    data = request.json
    book_id = data.get('book_id')
    try:
        book = Book.objects(id=book_id).first()
    except (DoesNotExist, ValidationError):
        return jsonify({'error': 'Book ID không hợp lệ'}), 400
    if not book or book.quantity <= 0:
        return jsonify({'error': 'Sách không tồn tại hoặc đã hết'}), 404
    book.update(dec__quantity=1)
    cache.clear()
    print("LOG: V2 Cache cleared.")
    new_record = BorrowRecord(user_id=str(current_user.id), username=current_user.username, book_id=str(book.id),
                              book_title=book.title)
    new_record.save()
    return jsonify({'message': f"Mượn sách '{book.title}' thành công", 'record': new_record.to_dict()}), 201


@v2_bp.route('/borrow-records/<string:record_id>', methods=['PUT'])
@token_required
def return_book_v2(current_user, record_id):
    """
    Trả sách (V2)
    ---
    tags: [Borrowing V2]
    security:
      - APIKeyHeader: []
    parameters:
      - name: record_id
        in: path
        type: string
        required: true
    responses:
      200: {description: Trả sách thành công.}
      403: {description: Không có quyền.}
      404: {description: Không tìm thấy phiếu.}
    """
    # Logic không đổi so với V1
    try:
        record = BorrowRecord.objects(id=record_id).first()
    except (DoesNotExist, ValidationError):
        return jsonify({'error': 'Phiếu mượn không hợp lệ'}), 400
    if not record: return jsonify({'error': 'Không tìm thấy phiếu mượn'}), 404
    if record.user_id != str(current_user.id): return jsonify({'error': 'Không có quyền trả phiếu này'}), 403
    if record.returned: return jsonify({'message': 'Sách này đã được trả từ trước'}), 200
    cache.clear()
    print("LOG: V2 Cache cleared.")
    Book.objects(id=record.book_id).update(inc__quantity=1)
    record.update(returned=True, return_date=datetime.utcnow())
    return jsonify({'message': f"Trả sách '{record.book_title}' thành công"}), 200


# ======================================================================
# --- SECTION 7: REGISTER BLUEPRINTS & RUN APP (Chạy ứng dụng) ---
# ======================================================================

@app.route('/')
def index():
    # Trang index này có thể dùng để render index2.html
    return render_template('index2.html')


# --- ĐĂNG KÝ CÁC BLUEPRINT VỚI FLASK APP ---
app.register_blueprint(v1_bp)  # Đăng ký V1
app.register_blueprint(v2_bp)  # Đăng ký V2

# ---------------------------------------------

if __name__ == '__main__':
    # --- KHỐI THÊM DỮ LIỆU MẪU (SEEDING) ---
    # Chỉ chạy khi chạy file trực tiếp
    if Book.objects.count() == 0:
        print("Database rỗng. Thêm 20 sách mẫu...")
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
        books_to_insert = [Book(**data) for data in sample_books_data]
        Book.objects.insert(books_to_insert)
        print(f"Đã thêm thành công {len(books_to_insert)} sách.")
    else:
        print("Database đã có dữ liệu sách. Bỏ qua seeding.")
    # ----------------------------------------

    app.run(debug=True)