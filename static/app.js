(() => {
  const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content || '';
  const siteHeader = document.querySelector('.site-header');
  const readingProgress = document.querySelector('[data-reading-progress]');
  const updateReadingPosition = () => {
    const range = Math.max(document.documentElement.scrollHeight - innerHeight, 1);
    if (readingProgress) readingProgress.style.width = `${Math.min(1, Math.max(0, scrollY / range)) * 100}%`;
    siteHeader?.classList.toggle('is-compact', scrollY > 36);
  };
  updateReadingPosition();
  addEventListener('scroll', updateReadingPosition, {passive:true});
  addEventListener('resize', updateReadingPosition, {passive:true});

  document.querySelectorAll('.reveal').forEach((element) => element.classList.add('is-visible'));

  const trackEvent = async (eventName, {ideaSlug='', eventValue='', keepalive=false}={}) => {
    const response = await fetch('/api/events', {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()}, body:JSON.stringify({event_name:eventName, idea_slug:ideaSlug, event_value:eventValue}), keepalive});
    if (!response.ok) throw new Error('analytics event rejected');
    return response.status === 204 ? {} : response.json();
  };

  const filterButtons = [...document.querySelectorAll('[data-filter]')];
  const applyIdeaFilter = (requested, track=false) => {
    if (!filterButtons.length) return;
    const available = new Set(filterButtons.map((button) => button.dataset.filter || 'all'));
    const filter = available.has(requested) ? requested : 'all';
    filterButtons.forEach((button) => { const active=(button.dataset.filter||'all')===filter; button.classList.toggle('is-active',active); button.setAttribute('aria-pressed',String(active)); });
    let visibleCount=0;
    document.querySelectorAll('.idea-card').forEach((card) => {
      const visible=filter==='all'||(card.dataset.tags||'').split(',').includes(filter);
      card.hidden=!visible; card.setAttribute('aria-hidden',String(!visible));
      card.querySelectorAll('a,button,input,select,textarea').forEach((control)=>visible?control.removeAttribute('tabindex'):control.setAttribute('tabindex','-1'));
      if(visible) visibleCount+=1;
    });
    const result=document.querySelector('#idea-result-count');
    if(result) result.textContent=filter==='all'?`目前顯示全部 ${visibleCount} 卷`:`${filter}・找到 ${visibleCount} 卷`;
    const empty=document.querySelector('#idea-filter-empty'); if(empty) empty.hidden=visibleCount>0;
    const url=new URL(location.href); if(filter==='all') url.searchParams.delete('filter'); else url.searchParams.set('filter',filter); history.replaceState(null,'',`${url.pathname}${url.search}${url.hash}`);
    if(track) trackEvent('filter_used',{eventValue:filter}).catch(()=>{});
  };
  filterButtons.forEach((button)=>button.addEventListener('click',()=>applyIdeaFilter(button.dataset.filter||'all',true)));
  document.querySelector('[data-reset-idea-filter]')?.addEventListener('click',()=>applyIdeaFilter('all',true));
  if(filterButtons.length) applyIdeaFilter(new URL(location.href).searchParams.get('filter')||'all');

  const detail=document.querySelector('[data-analytics-idea]');
  if(detail){
    const ideaSlug=detail.dataset.analyticsIdea||''; const sent=new Set();
    const depth=()=>{const rect=detail.getBoundingClientRect(); const ratio=rect.height?Math.max(0,Math.min(rect.height,innerHeight-rect.top))/rect.height:0; [50,90].forEach((threshold)=>{if(ratio>=threshold/100&&!sent.has(threshold)){sent.add(threshold);trackEvent('reading_depth',{ideaSlug,eventValue:String(threshold)}).catch(()=>{});}})};
    depth(); addEventListener('scroll',depth,{passive:true});
    const button=document.querySelector('[data-interest-cta]'); const status=document.querySelector('[data-interest-status]'); const key=`twyb:interest:${ideaSlug}`;
    const marked=()=>{if(!button)return;button.textContent='已記下開放意願';button.disabled=true;if(status)status.textContent='已記錄匿名意願；沒有建立訂單，也沒有傳送個人資料。';};
    try{if(localStorage.getItem(key)==='1')marked();}catch(_error){}
    button?.addEventListener('click',async()=>{button.disabled=true;if(status)status.textContent='正在安全記錄…';try{await trackEvent('interest_registered',{ideaSlug});try{localStorage.setItem(key,'1');}catch(_error){}marked();}catch(_error){button.disabled=false;if(status)status.textContent='目前無法記錄，請稍後再試。';}});
  }

  const orderForm=document.querySelector('#order-form');
  if(orderForm){
    const dialog=document.querySelector('#purchase-notice-dialog'); const error=document.querySelector('#purchase-notice-error'); const confirm=document.querySelector('[data-confirm-purchase]');
    confirm?.addEventListener('click',()=>{const purchase=orderForm.querySelector('[name="purchase_notice_consent"]');const digital=orderForm.querySelector('[name="digital_content_consent"]');if(!purchase?.checked||!digital?.checked){error.textContent='請勾選兩項確認後再繼續付款。';return;}error.textContent='';orderForm.dataset.noticeApproved='true';dialog?.close();orderForm.requestSubmit();});
    orderForm.addEventListener('submit',async(event)=>{event.preventDefault();const status=document.querySelector('#order-status');const submit=orderForm.querySelector('button[type="submit"]');const name=orderForm.querySelector('[name="customer_name"]');const email=orderForm.querySelector('[name="customer_email"]');if(!name.reportValidity()||!email.reportValidity())return;if(orderForm.dataset.noticeApproved!=='true'){if(typeof dialog?.showModal==='function')dialog.showModal();else dialog?.setAttribute('open','');return;}orderForm.dataset.noticeApproved='false';status.textContent='正在建立訂單…';submit.disabled=true;try{const form=new FormData(orderForm);const response=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf()},body:JSON.stringify({idea_slug:orderForm.dataset.ideaSlug,customer_name:form.get('customer_name'),customer_email:form.get('customer_email'),purchase_notice_consent:form.get('purchase_notice_consent')==='on',digital_content_consent:form.get('digital_content_consent')==='on'})});const data=await response.json();if(!response.ok)throw new Error(data.error||'建立訂單失敗');status.textContent='訂單已建立，正在前往付款…';location.assign(data.checkout_url);}catch(err){status.textContent=err.message||'建立訂單失敗，請稍後再試。';submit.disabled=false;}});
  }
  document.querySelectorAll('[data-dialog-close]').forEach((button)=>button.addEventListener('click',()=>button.closest('dialog')?.close()));
  document.querySelectorAll('dialog[data-auto-modal]').forEach((dialog)=>{if(typeof dialog.showModal!=='function')return;if(dialog.open)dialog.close();setTimeout(()=>dialog.showModal(),80);});
  const paymentForm=document.querySelector('[data-auto-submit-payment]'); if(paymentForm)setTimeout(()=>paymentForm.requestSubmit(),350);

})();
