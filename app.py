
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, abort
import os
import psycopg
from psycopg.rows import dict_row
from psycopg.errors import UniqueViolation
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid
import cloudinary
import cloudinary.uploader
from solapi import SolapiMessageService
from solapi.model import RequestMessage

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 필요합니다.")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
CLOUDINARY_CLOUD_NAME=os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY=os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET=os.environ.get("CLOUDINARY_API_SECRET")
SOLAPI_API_KEY=os.environ.get("SOLAPI_API_KEY")
SOLAPI_API_SECRET=os.environ.get("SOLAPI_API_SECRET")
SOLAPI_SENDER_NUMBER=os.environ.get("SOLAPI_SENDER_NUMBER")
ADMIN_PHONE=os.environ.get("ADMIN_PHONE")
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )

ALLOWED_EXTENSIONS={"png","jpg","jpeg","webp","gif"}

def normalize_phone(phone):
    return "".join(ch for ch in (phone or "") if ch.isdigit())

def send_sms(to, text):
    """SOLAPI 설정이 있으면 SMS/LMS를 발송합니다. 문자 실패가 주문 자체를 막지는 않습니다."""
    to=normalize_phone(to)
    if not all([SOLAPI_API_KEY,SOLAPI_API_SECRET,SOLAPI_SENDER_NUMBER,to]):
        return False
    try:
        service=SolapiMessageService(api_key=SOLAPI_API_KEY,api_secret=SOLAPI_API_SECRET)
        message=RequestMessage(from_=normalize_phone(SOLAPI_SENDER_NUMBER),to=to,text=text)
        service.send(message)
        return True
    except Exception as e:
        app.logger.exception("SMS 발송 실패: %s",e)
        return False

def save_image(file):
    if not file or not file.filename:
        return None, None
    ext=file.filename.rsplit(".",1)[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("지원하지 않는 이미지 형식입니다.")
    if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
        raise ValueError("Cloudinary 환경변수가 설정되지 않았습니다.")
    result=cloudinary.uploader.upload(
        file,
        folder="ono-market/products",
        resource_type="image"
    )
    return result["secure_url"], result["public_id"]

def delete_cloud_image(public_id):
    if not public_id:
        return
    try:
        cloudinary.uploader.destroy(public_id, resource_type="image")
    except Exception:
        pass

def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def init_db():
    con=db()
    with con.cursor() as cur:
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users(
          id BIGSERIAL PRIMARY KEY,
          email TEXT UNIQUE NOT NULL,
          password_hash TEXT NOT NULL,
          name TEXT NOT NULL,
          phone TEXT NOT NULL DEFAULT '',
          address TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT '정상',
          created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS points INTEGER NOT NULL DEFAULT 0")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS points_history(
          id BIGSERIAL PRIMARY KEY,
          user_id BIGINT NOT NULL,
          order_id BIGINT,
          amount INTEGER NOT NULL,
          description TEXT NOT NULL,
          created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS products(
          id BIGSERIAL PRIMARY KEY,
          name TEXT NOT NULL,
          category TEXT NOT NULL,
          price INTEGER NOT NULL,
          stock INTEGER NOT NULL DEFAULT 0,
          emoji TEXT DEFAULT '📦',
          description TEXT DEFAULT '',
          active INTEGER DEFAULT 1,
          main_image TEXT DEFAULT '',
          main_image_public_id TEXT DEFAULT ''
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders(
          id BIGSERIAL PRIMARY KEY,
          user_id BIGINT,
          customer_name TEXT NOT NULL,
          phone TEXT NOT NULL,
          address TEXT NOT NULL,
          memo TEXT DEFAULT '',
          total INTEGER NOT NULL,
          status TEXT DEFAULT '주문접수',
          created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
        )
        """)
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS points_awarded INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS points_used INTEGER NOT NULL DEFAULT 0")
        cur.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS subtotal INTEGER NOT NULL DEFAULT 0")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS order_items(
          id BIGSERIAL PRIMARY KEY,
          order_id BIGINT NOT NULL,
          product_id BIGINT NOT NULL,
          product_name TEXT NOT NULL,
          price INTEGER NOT NULL,
          qty INTEGER NOT NULL
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS product_images(
          id BIGSERIAL PRIMARY KEY,
          product_id BIGINT NOT NULL,
          filename TEXT NOT NULL,
          sort_order INTEGER NOT NULL DEFAULT 0,
          public_id TEXT DEFAULT ''
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS product_questions(
          id BIGSERIAL PRIMARY KEY,
          product_id BIGINT NOT NULL,
          user_id BIGINT NOT NULL,
          user_name TEXT NOT NULL,
          question TEXT NOT NULL,
          answer TEXT DEFAULT '',
          created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
          answered_at TIMESTAMPTZ
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS site_settings(
          id INTEGER PRIMARY KEY,
          shop_name TEXT NOT NULL DEFAULT 'ONO MARKET',
          hero_title TEXT NOT NULL DEFAULT 'GOOD THINGS, EVERY DAY.',
          hero_text TEXT NOT NULL DEFAULT '매일 쓰는 물건일수록, 더 좋은 것으로.',
          accent_color TEXT NOT NULL DEFAULT '#111827',
          background_color TEXT NOT NULL DEFAULT '#f6f6f2',
          hero_start TEXT NOT NULL DEFAULT '#e9e3d7',
          hero_end TEXT NOT NULL DEFAULT '#cbd5c0'
        )
        """)
        cur.execute("INSERT INTO site_settings(id) VALUES(1) ON CONFLICT (id) DO NOTHING")
        cur.execute("SELECT COUNT(*) AS c FROM products")
        if cur.fetchone()["c"] == 0:
            seed=[
              ("데일리 머그 2P","리빙",18900,20,"☕","매일 쓰기 좋은 심플한 머그 세트"),
              ("소프트 실리콘 식판","육아",23900,15,"🧸","부드럽고 관리가 쉬운 식판"),
              ("포근 코튼 타월 세트","리빙",32900,12,"🛁","도톰한 데일리 코튼 타월"),
              ("우드 핸들 커트러리","키친",27900,10,"🍴","따뜻한 무드의 커트러리"),
              ("데일리 베이비 빕","육아",15900,25,"👶","가볍고 편한 데일리 빕"),
              ("클리어 글라스 4P","키친",24900,8,"🥛","깔끔한 투명 글라스 세트")
            ]
            cur.executemany("INSERT INTO products(name,category,price,stock,emoji,description) VALUES(%s,%s,%s,%s,%s,%s)",seed)
    con.commit()
    con.close()

init_db()

def login_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("user_id"):
            flash("로그인이 필요합니다.")
            return redirect(url_for("login"))
        return f(*a, **kw)
    return wrap

def admin_required(f):
    @wraps(f)
    def wrap(*a, **kw):
        if not session.get("admin"): return redirect(url_for("admin_login"))
        return f(*a, **kw)
    return wrap

@app.context_processor
def inject_site():
    con=db()
    site=con.execute("SELECT * FROM site_settings WHERE id=1").fetchone()
    con.close()
    return {"site": site}

@app.get("/")
def home():
    con=db()
    products=con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall()
    current_user=None
    if session.get("user_id"):
        current_user=con.execute("SELECT * FROM users WHERE id=%s",(session["user_id"],)).fetchone()
    con.close()
    return render_template("index.html", products=products, products_json=[dict(p) for p in products], current_user=current_user)

@app.get("/cart")
def cart_page():
    con=db()
    products=con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall()
    con.close()
    return render_template("cart.html",products_json=[dict(p) for p in products])

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    con = db()
    product = con.execute(
        "SELECT * FROM products WHERE id=%s AND active=1",
        (product_id,)
    ).fetchone()
    if not product:
        con.close()
        abort(404)

    images = con.execute(
        "SELECT * FROM product_images WHERE product_id=%s ORDER BY sort_order,id",
        (product_id,)
    ).fetchall()
    questions = con.execute(
        "SELECT * FROM product_questions WHERE product_id=%s ORDER BY id DESC",
        (product_id,)
    ).fetchall()
    con.close()
    return render_template("product.html", product=product, images=images, questions=questions)

@app.post("/product/<int:product_id>/questions")
@login_required
def add_product_question(product_id):
    question=request.form.get("question","").strip()
    if not question:
        flash("문의 내용을 입력해주세요.")
        return redirect(url_for("product_detail",product_id=product_id)+"#product-qna")
    con=db()
    product=con.execute("SELECT id,name FROM products WHERE id=%s AND active=1",(product_id,)).fetchone()
    if not product:
        con.close()
        abort(404)
    con.execute("""INSERT INTO product_questions(product_id,user_id,user_name,question)
                   VALUES(%s,%s,%s,%s)""",
                (product_id,session["user_id"],session.get("user_name","회원"),question))
    con.commit()
    con.close()

    if ADMIN_PHONE:
        product_name=product.get("name","상품") if hasattr(product,"get") else "상품"
        preview=question.replace("\n"," ").strip()
        if len(preview)>50:
            preview=preview[:50]+"..."
        send_sms(
            ADMIN_PHONE,
            f"[ONO MARKET] 새 상품 문의 / 상품: {product_name} / 문의자: {session.get('user_name','회원')} / {preview}"
        )

    flash("상품 문의가 등록되었습니다.")
    return redirect(url_for("product_detail",product_id=product_id)+"#product-qna")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        email=request.form["email"].strip().lower()
        pw=request.form["password"]
        name=request.form["name"].strip()
        phone=request.form["phone"].strip()
        postcode=request.form.get("postcode","").strip()
        address=request.form.get("address","").strip()
        detail_address=request.form.get("detail_address","").strip()
        full_address=f"[{postcode}] {address} {detail_address}".strip()
        if len(pw)<6:
            flash("비밀번호는 6자 이상 입력해주세요."); return render_template("signup.html")
        if not address or not detail_address:
            flash("배송지 주소와 상세주소를 입력해주세요."); return render_template("signup.html")
        con=db()
        try:
            con.execute("INSERT INTO users(email,password_hash,name,phone,address) VALUES(%s,%s,%s,%s,%s)",
                        (email,generate_password_hash(pw),name,phone,full_address))
            con.commit(); flash("회원가입 완료! 로그인해주세요."); return redirect(url_for("login"))
        except UniqueViolation:
            flash("이미 가입된 이메일입니다.")
        finally: con.close()
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        con=db()
        u=con.execute("SELECT * FROM users WHERE email=%s",(request.form["email"].strip().lower(),)).fetchone()
        con.close()
        if u and check_password_hash(u["password_hash"],request.form["password"]):
            if u["status"]!="정상":
                flash("이용이 제한된 계정입니다."); return render_template("login.html")
            session["user_id"]=u["id"]; session["user_name"]=u["name"]
            return redirect(url_for("home"))
        flash("이메일 또는 비밀번호를 확인해주세요.")
    return render_template("login.html")

@app.get("/logout")
def logout():
    session.pop("user_id",None); session.pop("user_name",None)
    return redirect(url_for("home"))

@app.route("/mypage", methods=["GET","POST"])
@login_required
def mypage():
    con=db()
    if request.method=="POST":
        con.execute("UPDATE users SET name=%s,phone=%s,address=%s WHERE id=%s",
                    (request.form["name"],request.form["phone"],request.form["address"],session["user_id"]))
        con.commit(); session["user_name"]=request.form["name"]; flash("회원정보가 수정되었습니다.")
    u=con.execute("SELECT * FROM users WHERE id=%s",(session["user_id"],)).fetchone()
    points_history=con.execute("SELECT * FROM points_history WHERE user_id=%s ORDER BY id DESC LIMIT 50",(session["user_id"],)).fetchall()
    con.close()
    return render_template("mypage.html",u=u,points_history=points_history)

@app.get("/orders")
@login_required
def orders():
    con=db()
    orders=con.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC",(session["user_id"],)).fetchall()
    order_ids=[o["id"] for o in orders]
    items_by_order={}
    if order_ids:
        placeholders=",".join(["%s"]*len(order_ids))
        order_items=con.execute(f"SELECT * FROM order_items WHERE order_id IN ({placeholders}) ORDER BY order_id,id",order_ids).fetchall()
        for item in order_items:
            items_by_order.setdefault(item["order_id"],[]).append(item)
    con.close()
    return render_template("orders.html",orders=orders,items_by_order=items_by_order)

@app.post("/password")
@login_required
def password():
    con=db(); u=con.execute("SELECT * FROM users WHERE id=%s",(session["user_id"],)).fetchone()
    if not check_password_hash(u["password_hash"],request.form["current"]):
        con.close(); flash("현재 비밀번호가 틀렸습니다."); return redirect(url_for("mypage"))
    if len(request.form["new"])<6:
        con.close(); flash("새 비밀번호는 6자 이상이어야 합니다."); return redirect(url_for("mypage"))
    con.execute("UPDATE users SET password_hash=%s WHERE id=%s",(generate_password_hash(request.form["new"]),session["user_id"]))
    con.commit(); con.close(); flash("비밀번호를 변경했습니다.")
    return redirect(url_for("mypage"))

@app.post("/withdraw")
@login_required
def withdraw():
    con=db(); con.execute("UPDATE users SET status='탈퇴' WHERE id=%s",(session["user_id"],)); con.commit(); con.close()
    session.clear(); flash("회원 탈퇴 처리되었습니다."); return redirect(url_for("home"))

@app.post("/api/orders")
@login_required
def create_order():
    data=request.get_json(force=True)
    customer=data.get("customer",{})
    cart=data.get("cart",[])
    try:
        requested_points=max(0,int(data.get("points_used",0) or 0))
    except (TypeError,ValueError):
        return jsonify({"error":"포인트 사용 금액을 확인해주세요."}),400

    if not all([customer.get("name"),customer.get("phone"),customer.get("address")]) or not cart:
        return jsonify({"error":"주문 정보를 확인해주세요."}),400

    con=db()
    try:
        items=[]
        subtotal=0
        for x in cart:
            p=con.execute("SELECT * FROM products WHERE id=%s AND active=1 FOR UPDATE",(int(x["id"]),)).fetchone()
            qty=int(x["qty"])
            if not p or qty<1 or p["stock"]<qty:
                raise ValueError("상품 재고가 부족합니다.")
            subtotal += p["price"]*qty
            items.append((p,qty))

        user=con.execute("SELECT points FROM users WHERE id=%s FOR UPDATE",(session["user_id"],)).fetchone()
        available_points=user["points"] if user else 0
        points_used=min(requested_points,available_points,subtotal)
        total=subtotal-points_used

        cur=con.execute("""INSERT INTO orders(user_id,customer_name,phone,address,memo,total,subtotal,points_used)
                           VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (session["user_id"],customer["name"],customer["phone"],customer["address"],
                         customer.get("memo",""),total,subtotal,points_used))
        oid=cur.fetchone()["id"]

        if points_used>0:
            con.execute("UPDATE users SET points=points-%s WHERE id=%s",(points_used,session["user_id"]))
            con.execute("""INSERT INTO points_history(user_id,order_id,amount,description)
                           VALUES(%s,%s,%s,%s)""",
                        (session["user_id"],oid,-points_used,f"주문 #{oid} 결제 포인트 사용"))

        for p,qty in items:
            con.execute("INSERT INTO order_items(order_id,product_id,product_name,price,qty) VALUES(%s,%s,%s,%s,%s)",
                        (oid,p["id"],p["name"],p["price"],qty))
            con.execute("UPDATE products SET stock=stock-%s WHERE id=%s",(qty,p["id"]))

        con.commit()
        customer_sms=f"[ONO MARKET] 주문 #{oid} 접수 완료. 결제금액 {total:,}원"
        if points_used:
            customer_sms+=f" / 포인트 {points_used:,}P 사용"
        customer_sms+=". 주문조회에서 진행상태를 확인해주세요."
        send_sms(customer["phone"],customer_sms)
        if ADMIN_PHONE:
            send_sms(ADMIN_PHONE,f"[ONO MARKET] 새 주문 #{oid} / {customer['name']} / 결제 {total:,}원 / 포인트 {points_used:,}P")
        return jsonify({"ok":True,"order_id":oid,"total":total,"points_used":points_used})
    except ValueError as e:
        con.rollback()
        return jsonify({"error":str(e)}),409
    finally:
        con.close()

@app.route("/admin/login",methods=["GET","POST"])
def admin_login():
    if request.method=="POST" and request.form["password"]==ADMIN_PASSWORD:
        session["admin"]=True; return redirect(url_for("admin"))
    return render_template("admin_login.html")

@app.get("/admin/logout")
def admin_logout(): session.pop("admin",None); return redirect(url_for("home"))

@app.get("/admin")
@admin_required
def admin():
    init_db()
    con=db()
    products=con.execute("SELECT * FROM products ORDER BY id DESC").fetchall()
    orders=con.execute("SELECT * FROM orders ORDER BY id DESC").fetchall()
    users=con.execute("""SELECT u.*, COUNT(o.id) order_count, COALESCE(SUM(o.total),0) spent
                         FROM users u LEFT JOIN orders o ON u.id=o.user_id
                         GROUP BY u.id ORDER BY u.id DESC""").fetchall()
    settings=con.execute("SELECT * FROM site_settings WHERE id=1").fetchone()
    all_images=con.execute("SELECT * FROM product_images ORDER BY product_id,sort_order,id").fetchall()
    order_items=con.execute("SELECT * FROM order_items ORDER BY order_id,id").fetchall()
    questions=con.execute("""SELECT q.*, p.name AS product_name
                             FROM product_questions q
                             JOIN products p ON p.id=q.product_id
                             ORDER BY q.id DESC""").fetchall()
    images_by_product={}
    items_by_order={}
    for image in all_images: images_by_product.setdefault(image["product_id"],[]).append(image)
    for item in order_items: items_by_order.setdefault(item["order_id"],[]).append(item)
    con.close()
    return render_template("admin.html",products=products,orders=orders,users=users,settings=settings,images_by_product=images_by_product,items_by_order=items_by_order,questions=questions)

@app.post("/admin/questions/<int:qid>/answer")
@admin_required
def answer_product_question(qid):
    answer=request.form.get("answer","").strip()
    if not answer:
        flash("답변 내용을 입력해주세요.")
        return redirect(url_for("admin")+"#product-questions")
    con=db()
    con.execute("""UPDATE product_questions
                   SET answer=%s, answered_at=CURRENT_TIMESTAMP
                   WHERE id=%s""",(answer,qid))
    con.commit()
    con.close()
    flash("상품 문의 답변이 등록되었습니다.")
    return redirect(url_for("admin")+"#product-questions")

@app.post("/admin/design")
@admin_required
def admin_design():
    f=request.form
    con=db()
    con.execute("""UPDATE site_settings SET shop_name=%s, hero_title=%s, hero_text=%s,
                   accent_color=%s, background_color=%s, hero_start=%s, hero_end=%s WHERE id=1""",
                (f["shop_name"], f["hero_title"], f["hero_text"], f["accent_color"],
                 f["background_color"], f["hero_start"], f["hero_end"]))
    con.commit()
    con.close()
    return redirect(url_for("admin"))

@app.post("/admin/products")
@admin_required
def add_product():
    f=request.form
    con=None
    try:
        main_image,main_public_id=save_image(request.files.get("main_image"))
        main_image=main_image or ""
        main_public_id=main_public_id or ""
        con=db()
        cur=con.execute("""INSERT INTO products(name,category,price,stock,emoji,description,main_image,main_image_public_id)
        VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",(f["name"],f["category"],int(f["price"]),int(f["stock"]),f.get("emoji","📦"),f.get("description",""),main_image,main_public_id))
        pid=cur.fetchone()["id"]
        for order,file in enumerate(request.files.getlist("detail_images")):
            image_url,public_id=save_image(file)
            if image_url:
                con.execute("INSERT INTO product_images(product_id,filename,sort_order,public_id) VALUES(%s,%s,%s,%s)",(pid,image_url,order,public_id or ""))
        con.commit()
    except (ValueError, Exception) as e:
        if con: con.rollback()
        flash("이미지/상품 저장 오류: "+str(e))
    finally:
        if con: con.close()
    return redirect(url_for("admin"))

@app.post("/admin/products/<int:pid>/edit")
@admin_required
def edit_product(pid):
    f=request.form
    con=db()
    p=con.execute("SELECT * FROM products WHERE id=%s",(pid,)).fetchone()
    if not p:
        con.close()
        abort(404)
    try:
        new_url,new_public_id=save_image(request.files.get("main_image"))
        main_image=new_url or p["main_image"]
        main_public_id=new_public_id or p["main_image_public_id"]
        con.execute("""UPDATE products SET name=%s,category=%s,price=%s,stock=%s,emoji=%s,description=%s,main_image=%s,main_image_public_id=%s WHERE id=%s""",
        (f["name"],f["category"],int(f["price"]),int(f["stock"]),f.get("emoji","📦"),f.get("description",""),main_image,main_public_id,pid))
        if new_url:
            delete_cloud_image(p["main_image_public_id"])
        for order,file in enumerate(request.files.getlist("detail_images")):
            image_url,public_id=save_image(file)
            if image_url:
                con.execute("INSERT INTO product_images(product_id,filename,sort_order,public_id) VALUES(%s,%s,%s,%s)",(pid,image_url,order+100,public_id or ""))
        con.commit()
    except Exception as e:
        con.rollback()
        flash("상품 수정 오류: "+str(e))
    finally:
        con.close()
    return redirect(url_for("admin"))

@app.post("/admin/products/<int:pid>/main-image/delete")
@admin_required
def delete_main_product_image(pid):
    con=db()
    product=con.execute("SELECT main_image_public_id FROM products WHERE id=%s",(pid,)).fetchone()
    if product:
        con.execute("UPDATE products SET main_image='', main_image_public_id='' WHERE id=%s",(pid,))
        con.commit()
        delete_cloud_image(product["main_image_public_id"])
        flash("대표 이미지가 삭제되었습니다.")
    con.close()
    return redirect(url_for("admin"))

@app.post("/admin/product-images/<int:image_id>/delete")
@admin_required
def delete_product_image(image_id):
    con=db(); image=con.execute("SELECT * FROM product_images WHERE id=%s",(image_id,)).fetchone()
    if image:
        con.execute("DELETE FROM product_images WHERE id=%s",(image_id,)); con.commit()
        delete_cloud_image(image["public_id"])
        flash("상세 이미지가 삭제되었습니다.")
    con.close(); return redirect(url_for("admin"))

@app.post("/admin/products/<int:pid>/stock")
@admin_required
def stock(pid):
    con=db(); con.execute("UPDATE products SET stock=%s WHERE id=%s",(int(request.form["stock"]),pid)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/users/<int:uid>/status")
@admin_required
def user_status(uid):
    con=db(); con.execute("UPDATE users SET status=%s WHERE id=%s",(request.form["status"],uid)); con.commit(); con.close()
    return redirect(url_for("admin"))

@app.post("/admin/orders/<int:oid>/status")
@admin_required
def order_status(oid):
    status=request.form["status"]
    con=db()
    order=con.execute("SELECT * FROM orders WHERE id=%s FOR UPDATE",(oid,)).fetchone()
    if not order:
        con.close()
        abort(404)

    con.execute("UPDATE orders SET status=%s WHERE id=%s",(status,oid))
    awarded_points=0

    if status=="완료" and order["user_id"] and not order["points_awarded"]:
        awarded_points=int(order["total"] * 3 // 100)
        if awarded_points > 0:
            con.execute("UPDATE users SET points=points+%s WHERE id=%s",(awarded_points,order["user_id"]))
            con.execute("""INSERT INTO points_history(user_id,order_id,amount,description)
                           VALUES(%s,%s,%s,%s)""",
                        (order["user_id"],oid,awarded_points,f"주문 #{oid} 구매금액 3% 적립"))
        con.execute("UPDATE orders SET points_awarded=1 WHERE id=%s",(oid,))

    con.commit()
    con.close()

    send_sms(order["phone"],f"[ONO MARKET] 주문 #{oid} 상태가 '{status}'(으)로 변경되었습니다.")
    if awarded_points > 0:
        send_sms(order["phone"],f"[ONO MARKET] 주문 #{oid} 구매 적립금 {awarded_points:,}P가 적립되었습니다.")
    return redirect(url_for("admin"))

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=5000,debug=False)
