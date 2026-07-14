let basket=JSON.parse(localStorage.getItem("ono-cart")||"{}"),cat="전체";const won=n=>n.toLocaleString("ko-KR")+"원";function save(){localStorage.setItem("ono-cart",JSON.stringify(basket));renderCart()}function renderFilters(){let cs=["전체",...new Set(PRODUCTS.map(p=>p.category))];filters.innerHTML=cs.map(c=>`<button class="chip ${c===cat?'on':''}" onclick="cat='${c}';renderFilters();render()">${c}</button>`).join("")}function render(){let q=search.value.toLowerCase();grid.innerHTML=PRODUCTS.filter(p=>(cat==="전체"||p.category===cat)&&p.name.toLowerCase().includes(q)).map(p=>`<article class="card"><a href="/product/${p.id}"><div class="pic">${p.main_image?`<img src="${p.main_image}" alt="${p.name}">`:p.emoji}</div></a><div class="info"><div class="muted">${p.category} · 재고 ${p.stock}</div><a href="/product/${p.id}"><div class="name">${p.name}</div></a><div class="muted">${p.description}</div><div class="price">${won(p.price)}</div><div class="product-actions"><button ${p.stock<1?'disabled':''} onclick="add(${p.id})">${p.stock<1?'품절':'장바구니 담기'}</button><button class="buy-now" ${p.stock<1?'disabled':''} onclick="buyNow(${p.id})">${p.stock<1?'품절':'주문하기'}</button></div></div></article>`).join("")}function add(id){let p=PRODUCTS.find(x=>x.id==id);if(!p||p.stock<1)return;if((basket[id]||0)>=p.stock)return alert(`재고는 최대 ${p.stock}개까지 담을 수 있습니다.`);basket[id]=(basket[id]||0)+1;save()}function buyNow(id){let p=PRODUCTS.find(x=>x.id==id);if(!p||p.stock<1)return;basket={[id]:1};save();showOrder()}function qty(id,d){basket[id]=(basket[id]||0)+d;if(basket[id]<=0)delete basket[id];save()}function renderCart(){let es=Object.entries(basket),sum=0,n=0;items.innerHTML=es.map(([id,q])=>{let p=PRODUCTS.find(x=>x.id==id);if(!p)return"";sum+=p.price*q;n+=+q;return`<div class="cartitem rich-cart"><div class="cartpic">${p.main_image?`<img src="${p.main_image}" alt="${p.name}">`:`<span>${p.emoji}</span>`}</div><div class="cartdesc"><b>${p.name}</b><small>${won(p.price)}</small><div class="cartqty"><button onclick="qty(${id},-1)">−</button><span>${q}</span><button onclick="qty(${id},1)">＋</button><button class="remove" onclick="removeItem(${id})">삭제</button></div></div><strong>${won(p.price*q)}</strong></div>`}).join("")||"<p class='emptycart'>장바구니가 비어 있어요.</p>";total.textContent=won(sum);count.textContent=n;checkoutBtn.disabled=!n}function removeItem(id){delete basket[id];save()}function clearDrawerCart(){
  if(!Object.keys(basket).length)return alert("장바구니가 이미 비어 있어요.");
  if(!confirm("장바구니에 담긴 상품을 모두 삭제할까요?"))return;
  basket={};
  localStorage.setItem("ono-cart",JSON.stringify(basket));
  renderCart();
}
function openCart(){cartDrawer.classList.add("on");shade.classList.add("on")}function closeCart(){cartDrawer.classList.remove("on");shade.classList.remove("on")}let orderSubtotalValue=0;
function updatePointPayment(){
  let input=document.getElementById("pointsUsed");
  if(!input)return;
  let points=Math.max(0,Math.floor(Number(input.value)||0));
  points=Math.min(points,ONO_USER_POINTS,orderSubtotalValue);
  input.value=points;
  orderSubtotal.textContent=won(orderSubtotalValue);
  pointDiscount.textContent="-"+points.toLocaleString()+"P";
  payTotal.textContent=won(orderSubtotalValue-points);
}
function useAllPoints(){pointsUsed.value=Math.min(ONO_USER_POINTS,orderSubtotalValue);updatePointPayment()}
function showOrder(){if(!Object.keys(basket).length)return alert("상품을 담아주세요.");if(!ONO_LOGGED_IN){loginOrderModal.style.display="grid";return;}let sum=0;orderSummary.innerHTML=Object.entries(basket).map(([id,q])=>{let p=PRODUCTS.find(x=>x.id==id);if(!p)return"";sum+=p.price*q;return`<div class="orderline"><span>${p.name} × ${q}</span><b>${won(p.price*q)}</b></div>`}).join("");orderSubtotalValue=sum;pointsUsed.value=0;updatePointPayment();modal.style.display="grid"}function selectDeliveryMemo(value){
  const memo=document.getElementById("deliveryMemo");
  if(!memo)return;
  if(value==="직접입력"){
    memo.value="";
    memo.focus();
    return;
  }
  memo.value=value;
}
orderForm.onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target),customer=Object.fromEntries(f.entries());if(!customer.payment_method)return alert("결제수단을 선택해주세요.");customer.memo=`[결제수단: ${customer.payment_method}] ${customer.memo||""}`.trim();delete customer.payment_method;let body={customer,points_used:Number(pointsUsed.value)||0,cart:Object.entries(basket).map(([id,qty])=>({id:+id,qty}))};let r=await fetch("/api/orders",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}),d=await r.json();if(!r.ok)return alert(d.error);alert(`주문 접수 완료! 주문번호 #${d.order_id}\n포인트 ${Number(d.points_used).toLocaleString()}P 사용\n최종 결제금액 ${Number(d.total).toLocaleString()}원\n현재는 실제 PG 승인 전 테스트 결제 단계입니다.`);basket={};save();location.href="/mypage"};search.oninput=render;renderFilters();render();renderCart();
const pageParams=new URLSearchParams(location.search);
if(pageParams.get("cart")==="1"){openCart();history.replaceState({},document.title,"/")}
if(pageParams.get("order")==="1"){showOrder();history.replaceState({},document.title,"/")}
document.addEventListener("input",e=>{if(e.target&&e.target.id==="pointsUsed")updatePointPayment()});
