let basket=JSON.parse(localStorage.getItem("ono-cart")||"{}");
const won=n=>Number(n).toLocaleString("ko-KR")+"원";
function saveCart(){localStorage.setItem("ono-cart",JSON.stringify(basket));renderCartPage()}
function changeQty(id,d){
  const p=PRODUCTS.find(x=>x.id==id);
  if(!p)return;
  basket[id]=(basket[id]||0)+d;
  if(basket[id]<=0)delete basket[id];
  else if(basket[id]>p.stock){basket[id]=p.stock;alert(`재고는 최대 ${p.stock}개까지 담을 수 있습니다.`)}
  saveCart();
}
function deleteCartItem(id){delete basket[id];saveCart()}
function clearCart(){
  if(!Object.keys(basket).length)return alert("장바구니가 이미 비어 있어요.");
  if(!confirm("장바구니에 담긴 상품을 모두 삭제할까요?"))return;
  basket={};
  saveCart();
}
function renderCartPage(){
  let rows=[],sum=0,count=0;
  for(const [id,q] of Object.entries(basket)){
    const p=PRODUCTS.find(x=>x.id==id);
    if(!p)continue;
    sum+=p.price*q;count+=Number(q);
    rows.push(`<div class="cart-page-item">
      <a href="/product/${p.id}" class="cart-page-pic">${p.main_image?`<img src="${p.main_image}" alt="${p.name}">`:`<span>${p.emoji}</span>`}</a>
      <div class="cart-page-desc"><small>${p.category}</small><a href="/product/${p.id}"><b>${p.name}</b></a><span>${won(p.price)}</span>
        <div class="cart-page-qty"><button onclick="changeQty(${p.id},-1)">−</button><strong>${q}</strong><button onclick="changeQty(${p.id},1)">＋</button><button class="cart-page-delete" onclick="deleteCartItem(${p.id})">삭제</button></div>
      </div><strong class="cart-page-line-total">${won(p.price*q)}</strong>
    </div>`);
  }
  cartPageItems.innerHTML=rows.join("");
  cartPageEmpty.style.display=rows.length?"none":"block";
  cartPageSummary.style.display=rows.length?"block":"none";
  cartPageCount.textContent=count.toLocaleString()+"개";
  cartPageTotal.textContent=won(sum);
}
function goCheckout(){
  if(!Object.keys(basket).length)return;
  location.href="/?order=1";
}
renderCartPage();