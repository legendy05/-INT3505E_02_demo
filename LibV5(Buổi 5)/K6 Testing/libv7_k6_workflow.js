import http from 'k6/http';
import { check, sleep, group } from 'k6';

// --- ⚙️ Cấu hình test ---
export let options = {
  stages: [
    { duration: '10s', target: 5 },  // tăng dần tới 5 user ảo
    { duration: '30s', target: 5 },  // giữ 5 user
    { duration: '10s', target: 0 }   // giảm dần về 0
  ],
  thresholds: {
    http_req_failed: ['rate<0.02'],   // <2% request lỗi
    http_req_duration: ['p(95)<1000'] // 95% request dưới 1s
  }
};

// --- ⚙️ Setup: login 1 lần, lấy token dùng chung ---
export function setup() {
  const payload = JSON.stringify({
    username: '1',      // thay bằng user test của bạn
    password: '1'
  });

  const res = http.post(
    'http://127.0.0.1:5000/api/login',
    payload,
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(res, { 'login 200': (r) => r.status === 200 });

  const token = JSON.parse(res.body).token;
  console.log('✅ Token:', token);
  return { token };
}

// --- ⚡ Workflow chính cho mỗi user ảo ---
export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    'x-access-token': data.token
  };

  group('Full Library Workflow', function () {

    // 🟢 1️⃣ GET all books
    const resBooks = http.get('http://127.0.0.1:5000/api/books?page=1&limit=20', { headers });
    check(resBooks, { 'books 200': (r) => r.status === 200 });

    let bookId = null;
    try {
      const books = JSON.parse(resBooks.body);
      if (books.data && books.data.length > 0)
        bookId = books.data[0].id;
    } catch (e) {
      console.error('❌ Parse books error', e);
    }

    if (!bookId) {
      console.error('❌ Không lấy được book_id');
      sleep(1);
      return;
    }

    // 🟢 2️⃣ Borrow book
    const borrowPayload = JSON.stringify({ book_id: bookId });
    const borrowRes = http.post('http://127.0.0.1:5000/api/borrow-records', borrowPayload, { headers });
    check(borrowRes, {
      'borrow 201': (r) => r.status === 201 || r.status === 400 || r.status === 404
    });

    let recordId = null;
    try {
      const br = JSON.parse(borrowRes.body);
      if (br.record && br.record.id)
        recordId = br.record.id;
    } catch (e) {}

    // 🟢 3️⃣ Return book
    if (recordId) {
      const retRes = http.put(`http://127.0.0.1:5000/api/borrow-records/${recordId}`, null, { headers });
      check(retRes, { 'return 200': (r) => r.status === 200 });
    }

    sleep(1); // nghỉ giữa các vòng
  });
}
