
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

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL 환경변수가 필요합니다.")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "change-me")
CLOUDINARY_CLOUD_NAME=os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY=os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET=os.environ.get("CLOUDINARY_API_SECRET")
if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )

ALLOWED_EXTENSIONS={"png","jpg","jpeg","webp","gif"}

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
    con=db(); products=con.execute("SELECT * FROM products WHERE active=1 ORDER BY id DESC").fetchall(); con.close()
    return render_template("index.html", products=products, products_json=[dict(p) for p in products])

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
    con.close()
    return render_template("product.html", product=product, images=images)

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method=="POST":
        email=request.form["email"].strip().lower()
        pw=request.form["password"]
        name=request.form["name"].strip()
        phone=request.form["phone"].strip()
        if len(pw)<6:
            flash("비밀번호는 6자 이상 입력해주세요."); return render_template("signup.html")
        con=db()
        try:
            con.execute("INSERT INTO users(email,password_hash,name,phone) VALUES(%s,%s,%s,%s)",
                        (email,generate_password_hash(pw),name,phone))
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
    orders=con.execute("SELECT * FROM orders WHERE user_id=%s ORDER BY id DESC",(session["user_id"],)).fetchall()
    con.close()
    return render_template("mypage.html",u=u,orders=orders)

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
def create_order():
    data=request.get_json(force=True); customer=data.get("customer",{}); cart=data.get("cart",[])
    if not all([customer.get("name"),customer.get("phone"),customer.get("address")]) or not cart:
        return jsonify({"error":"주문 정보를 확인해주세요."}),400
    con=db()
    try:
        items=[]; total=0
        for x in cart:
            p=con.execute("SELECT * FROM products WHERE id=%s AND active=1 FOR UPDATE",(int(x["id"]),)).fetchone()
            qty=int(x["qty"])
            if not p or qty<1 or p["stock"]<qty: raise ValueError("상품 재고가 부족합니다.")
            total += p["price"]*qty; items.append((p,qty))
        cur=con.execute("""INSERT INTO orders(user_id,customer_name,phone,address,memo,total)
                           VALUES(%s,%s,%s,%s,%s,%s) RETURNING id""",(session.get("user_id"),customer["name"],customer["phone"],
                           customer["address"],customer.get("memo",""),total))
        oid=cur.fetchone()["id"]
        for p,qty in items:
            con.execute("INSERT INTO order_items(order_id,product_id,product_name,price,qty) VALUES(%s,%s,%s,%s,%s)",
                        (oid,p["id"],p["name"],p["price"],qty))
            con.execute("UPDATE products SET stock=stock-%s WHERE id=%s",(qty,p["id"]))
        con.commit(); return jsonify({"ok":True,"order_id":oid})
    except ValueError as e:
        con.rollback(); return jsonify({"error":str(e)}),409
    finally: con.close()

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
    images_by_product={}
    for image in all_images: images_by_product.setdefault(image["product_id"],[]).append(image)
    con.close()
    return render_template("admin.html",products=products,orders=orders,users=users,settings=settings,images_by_product=images_by_product)

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

@app.post("/admin/product-images/<int:image_id>/delete")
@admin_required
def delete_product_image(image_id):
    con=db(); image=con.execute("SELECT * FROM product_images WHERE id=%s",(image_id,)).fetchone()
    if image:
        con.execute("DELETE FROM product_images WHERE id=%s",(image_id,)); con.commit()
        delete_cloud_image(image["public_id"])
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
    con=db(); con.execute("UPDATE orders SET status=%s WHERE id=%s",(request.form["status"],oid)); con.commit(); con.close()
    return redirect(url_for("admin"))

if __name__=="__main__":
    init_db()
    app.run(host="0.0.0.0",port=5000,debug=False)
