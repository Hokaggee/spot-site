(() => {
  const $ = selector => document.querySelector(selector);
  const el = (tag, className, text) => {const node=document.createElement(tag);if(className)node.className=className;if(text!==undefined)node.textContent=text;return node;};
  let csrf = '', album = null, busy = false, pending = [];
  const today = () => new Intl.DateTimeFormat('sv-SE', {timeZone:'Asia/Yakutsk'}).format(new Date());
  const dateLabel = value => new Intl.DateTimeFormat('ru-RU',{day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Yakutsk'}).format(new Date(value+'T12:00:00+09:00'));
  async function api(path, method='GET', data) {
    const headers = {'X-CSRF-Token':csrf};
    let body;
    if (data instanceof File) {body=data;headers['Content-Type']=data.type||'application/octet-stream';headers['X-Filename']=encodeURIComponent(data.name);}
    else if(data!==undefined){body=JSON.stringify(data);headers['Content-Type']='application/json';}
    const response=await fetch(path,{method,headers,body});
    const payload=await response.json();
    if(!response.ok){if(response.status===401&&!path.endsWith('login')){csrf='';$('#workspace').hidden=true;$('#login-panel').hidden=false;$('#logout').hidden=true;$('#login-title').textContent='Вход';$('#login-description').textContent='Войди снова — загрузка продолжится с того же места.';$('#login-submit').textContent='Войти';}throw new Error(payload.error||'Не удалось выполнить действие. Попробуй ещё раз.');}
    return payload;
  }
  function setBusy(value) {
    busy=value;
    for(const node of document.querySelectorAll('#workspace button,#workspace input,#logout'))node.disabled=value;
    $('#drop-zone').setAttribute('aria-disabled',String(value));
  }
  function notice(message,error=false){$(error?'#editor-error':'#save-note').textContent=message;}
  function values(){return{title:$('#album-name').value.trim(),date:$('#album-date').value};}
  function valid(){return $('#album-name').reportValidity()&&$('#album-date').reportValidity();}
  function updateState(){
    $('#editor-title').textContent=album?'Редактирование альбома':'Новый альбом';
    $('#album-state').textContent=album?.published?'На сайте':'Черновик';
    $('#album-state').classList.toggle('published',!!album?.published);
    $('#publish').textContent=album?.published?'Сохранить изменения':'Опубликовать альбом';
    $('#save-draft').textContent=album?.published?'Сохранить без снятия с сайта':'Сохранить черновик';
    $('#cover-help').hidden=!album?.photos.length;
  }
  function renderPhotos(){
    const grid=$('#editor-photos');grid.replaceChildren();
    for(const [index,photo] of (album?.photos||[]).entries()){
      const tile=el('div','edit-photo'),choose=el('button','cover-choice');choose.type='button';choose.disabled=busy;choose.setAttribute('aria-pressed',String(album.cover_id===photo.id));choose.setAttribute('aria-label',`Выбрать обложкой фотографию ${index+1}`);
      const img=el('img');img.src=photo.thumb_url;img.alt=photo.filename;img.loading='lazy';choose.append(img);
      if(album.cover_id===photo.id)choose.append(el('span','cover-label','✓ Обложка'));
      choose.addEventListener('click',async()=>{if(busy)return;setBusy(true);try{album=await api(`/api/admin/albums/${album.id}`,'PATCH',{cover_id:photo.id});notice('Обложка сохранена.');}catch(error){notice(error.message,true);}finally{setBusy(false);renderPhotos();}});
      const remove=el('button','delete-photo','×');remove.type='button';remove.disabled=busy;remove.setAttribute('aria-label',`Удалить фотографию ${index+1}`);
      remove.addEventListener('click',async()=>{if(busy||!confirm('Удалить эту фотографию из альбома?'))return;setBusy(true);try{await api(`/api/admin/albums/${album.id}/photos/${photo.id}`,'DELETE');album=await api(`/api/admin/albums/${album.id}`);await loadSaved();notice('Фотография удалена.');}catch(error){notice(error.message,true);}finally{setBusy(false);renderPhotos();updateState();}});
      tile.append(choose,remove,el('p','photo-name',photo.filename));grid.append(tile);
    }
    updateState();
  }
  async function ensureAlbum(){
    if(!album)album=await api('/api/admin/albums','POST',values());
    else album=await api(`/api/admin/albums/${album.id}`,'PATCH',values());
  }
  async function uploadFiles(files){
    if(busy)return;
    $('#upload-errors').textContent='';$('#editor-error').textContent='';
    pending.push(...files);
    if(!$('#album-name').value.trim()||!$('#album-date').value){notice(`Выбрано фото: ${pending.length}. Укажи название и дату — загрузка начнётся автоматически.`);$('#album-name').focus();return;}
    if(!valid())return;
    const batch=pending.splice(0),errors=[];let completed=0,started=false;
    setBusy(true);$('#upload-progress').hidden=false;$('#progress').value=0;
    try{
      await ensureAlbum();
      started=true;
      for(const [index,file] of batch.entries()){
        $('#upload-label').textContent=`Загружаем ${index+1} из ${batch.length}: ${file.name}`;
        if(file.size>40*1024*1024){errors.push(`${file.name}: размер больше 40 МБ.`);}
        else {
          try{const photo=await api(`/api/admin/albums/${album.id}/photos`,'POST',file);album.photos.push(photo);album.photo_count=album.photos.length;if(!album.cover_id)album.cover_id=photo.id;completed++;renderPhotos();}
          catch(error){errors.push(`${file.name}: ${error.message}`);if(!csrf){pending.push(...batch.slice(index));break;}}
        }
        $('#progress').value=Math.round((index+1)/batch.length*100);
      }
      notice(`Сохранено фотографий: ${completed}. ${album.published?'Они уже доступны на сайте.':'Выбери обложку и нажми «Опубликовать альбом».'}`);
      if(csrf)await loadSaved();
    }catch(error){if(!started)pending.unshift(...batch);errors.push(error.message);}
    finally{setBusy(false);renderPhotos();$('#photo-input').value='';$('#upload-label').textContent=pending.length&&!csrf?`Загрузка приостановлена. Уже сохранено: ${completed}. После входа продолжим оставшиеся ${pending.length}.`:`Сохранено ${completed} из ${batch.length} выбранных фотографий.${errors.length?' Некоторые файлы не загрузились — смотри сообщения ниже.':' Загрузка завершена.'}`;$('#upload-errors').textContent=errors.join('\n');}
  }
  async function save(publish){
    if(busy||!valid())return;
    if(pending.length){await uploadFiles([]);if(pending.length||!csrf)return;}
    setBusy(true);$('#editor-error').textContent='';
    try{
      await ensureAlbum();
      if(publish)album=await api(`/api/admin/albums/${album.id}`,'PATCH',{published:true});
      updateState();await loadSaved();notice(publish?'Готово! Альбом опубликован на сайте.':'Изменения сохранены.');
    }catch(error){notice(error.message,true);}
    finally{setBusy(false);}
  }
  function newAlbum(){
    if(busy)return;
    if(pending.length&&!confirm('Выбранные файлы ещё не загружены. Начать другой альбом?'))return;
    album=null;pending=[];$('#album-form').reset();$('#album-date').value=today();$('#upload-errors').textContent='';$('#editor-error').textContent='';$('#upload-progress').hidden=true;
    notice('Фотографии сначала сохранятся в черновике.');renderPhotos();
  }
  async function editAlbum(id){
    if(busy)return;
    if(pending.length&&!confirm('Есть ещё не загруженные файлы. Открыть другой альбом?'))return;
    setBusy(true);
    try{album=await api(`/api/admin/albums/${id}`);pending=[];$('#album-name').value=album.title;$('#album-date').value=album.date;$('#editor-error').textContent='';$('#upload-errors').textContent='';$('#upload-progress').hidden=true;notice('Изменения названия сохранятся после нажатия кнопки.');renderPhotos();$('#editor').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
    catch(error){notice(error.message,true);}
    finally{setBusy(false);}
  }
  async function loadSaved(){
    const {albums}=await api('/api/admin/albums');
    const list=$('#saved-albums');list.replaceChildren();$('#saved-empty').hidden=!!albums.length;$('#saved-count').textContent=albums.length?String(albums.length):'';
    for(const saved of albums){
      const item=el('article','saved-album');
      const cover=saved.cover_url?el('img','saved-thumb'):el('div','saved-thumb');if(saved.cover_url){cover.src=saved.cover_url;cover.alt='';cover.loading='lazy';}
      const info=el('div','saved-info');info.append(el('h3',null,saved.title),el('p',null,`${dateLabel(saved.date)} · ${saved.photo_count} фото · ${saved.published?'На сайте':'Черновик'}`));
      const actions=el('div','saved-actions'),edit=el('button','button secondary','Изменить');edit.type='button';edit.disabled=busy;edit.addEventListener('click',()=>editAlbum(saved.id));actions.append(edit);
      if(saved.published){const hide=el('button','button secondary','Скрыть с сайта');hide.type='button';hide.disabled=busy;hide.addEventListener('click',async()=>{if(busy)return;setBusy(true);try{const updated=await api(`/api/admin/albums/${saved.id}`,'PATCH',{published:false});if(album?.id===saved.id){album=updated;updateState();}await loadSaved();notice('Альбом скрыт с сайта. Фотографии сохранены.');}catch(error){notice(error.message,true);}finally{setBusy(false);}});actions.append(hide);}
      item.append(cover,info,actions);list.append(item);
    }
  }
  $('#login-form').addEventListener('submit',async event=>{
    event.preventDefault();$('#login-submit').disabled=true;$('#login-error').textContent='';
    try{const response=await api('/api/admin/login','POST',{username:$('#username').value.trim(),password:$('#password').value});csrf=response.csrf;$('#password').value='';$('#login-panel').hidden=true;$('#workspace').hidden=false;$('#logout').hidden=false;if(!album&&!pending.length)newAlbum();else if(album){album=await api(`/api/admin/albums/${album.id}`);renderPhotos();}await loadSaved();if(pending.length)await uploadFiles([]);}
    catch(error){$('#login-error').textContent=error.message;}
    finally{$('#login-submit').disabled=false;}
  });
  $('#logout').addEventListener('click',async()=>{if(busy)return;try{await api('/api/admin/logout','POST',{});location.reload();}catch(error){notice(error.message,true);}});
  $('#album-form').addEventListener('submit',event=>{event.preventDefault();save(true);});
  $('#save-draft').addEventListener('click',()=>save(false));
  $('#new-album').addEventListener('click',()=>{newAlbum();$('#album-name').focus();});
  $('#photo-input').addEventListener('change',event=>uploadFiles([...event.target.files]));
  for(const field of ['#album-name','#album-date'])$(field).addEventListener('change',()=>{if(pending.length&&!busy&&$('#album-name').value.trim()&&$('#album-date').value)uploadFiles([]);});
  const drop=$('#drop-zone');
  drop.addEventListener('dragover',event=>{event.preventDefault();if(!busy)drop.classList.add('drag-over');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('drag-over'));
  drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('drag-over');if(!busy)uploadFiles([...event.dataTransfer.files]);});
  window.addEventListener('beforeunload',event=>{if(busy||pending.length){event.preventDefault();event.returnValue='';}});
  async function initialize(){
    try{
      const session=await api('/api/admin/session');csrf=session.csrf||'';
      if(session.authenticated){$('#workspace').hidden=false;$('#logout').hidden=false;newAlbum();await loadSaved();}
      else{
        $('#login-panel').hidden=false;
        if(!session.configured){$('#login-form').hidden=true;$('#login-description').textContent='Доступ ещё не настроен. Обратитесь к администратору сайта.';}
      }
      $('#initial-status').hidden=true;
    }catch{$('#initial-status').textContent='Редактор недоступен. Проверь, что сайт запущен через server.py.';}
  }
  initialize();
})();
