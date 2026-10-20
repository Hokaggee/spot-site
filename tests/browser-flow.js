async page => {
  page = await page.context().newPage();
  const assert = (value, message) => {if(!value)throw new Error(message);};
  const base='http://127.0.0.1:8082';
  await page.goto(base+'/admin');
  await page.waitForFunction(()=>document.querySelector('#initial-status').hidden);
  if(await page.locator('#login-panel').isVisible()){
    await page.getByLabel('Логин',{exact:true}).fill('admin');await page.getByLabel('Пароль',{exact:true}).fill('spot-qa-only-password');
    await page.getByRole('button',{name:'Войти',exact:true}).click();
  }
  await page.locator('#workspace').waitFor({state:'visible'});
  await page.getByLabel('Название вечеринки').fill('Проверка фотоальбома');
  await page.getByLabel('Дата вечеринки').fill('2026-10-16');
  await page.locator('#photo-input').setInputFiles([
    '/Users/ivan/Downloads/spot-site/assets/moment-01.png',
    '/Users/ivan/Downloads/spot-site/assets/moment-02.png',
    '/Users/ivan/Downloads/spot-site/assets/moment-03.png'
  ]);
  await page.waitForFunction(()=>document.querySelectorAll('.cover-choice').length===3&&!document.querySelector('#publish').disabled);
  assert(await page.locator('.cover-choice').count()===3,'All photos must upload');
  let publicAlbums=await page.request.get(base+'/api/albums');
  const previousCount=(await publicAlbums.json()).albums.length;
  await page.getByRole('button',{name:'Выбрать обложкой фотографию 2',exact:true}).click();
  await page.waitForFunction(()=>document.querySelectorAll('.cover-choice')[1].getAttribute('aria-pressed')==='true'&&!document.querySelector('#publish').disabled);
  await page.getByRole('button',{name:'Опубликовать альбом',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#album-state').textContent==='На сайте'&&!document.querySelector('#publish').disabled);
  await page.goto(base+'/');
  await page.locator('.album-card').first().waitFor();
  assert(await page.locator('.album-card').count()===previousCount+1,'Only published album appears');
  await page.locator('.event').first().waitFor({timeout:15000});
  assert(await page.locator('.event').count()>=4,'Qtickets HTTP synchronization includes venue events');
  const hrefs=await page.locator('.event .button').evaluateAll(nodes=>nodes.map(n=>n.href));
  assert(hrefs.every(url=>['blagoveshensk.qtickets.events','afisha.yandex.ru'].includes(new URL(url).hostname)),'Ticket purchases go to the original seller');
  await page.locator('.album-card').first().click();
  await page.locator('.photo-tile').first().waitFor();
  assert(await page.locator('.photo-tile').count()===3,'Album opens all three uploaded photos');
  const archiveHref=await page.locator('#download-album').getAttribute('href');
  const zip=await page.request.get(base+archiveHref);
  assert(zip.status()===200&&zip.headers()['content-type']==='application/zip','Full album downloads as ZIP');
  await page.getByRole('button',{name:'Открыть фотографию 1 из 3',exact:true}).click();
  await page.getByRole('button',{name:'Следующая фотография',exact:true}).click();
  assert(await page.locator('#photo-counter').textContent()==='2 / 3','Photo navigation works');
  const originalHref=await page.locator('#download-photo').getAttribute('href');
  const original=await page.request.get(base+originalHref);
  assert(original.status()===200&&original.headers()['content-disposition'].startsWith('attachment;'),'Original photo downloads as attachment');
  await page.keyboard.press('ArrowRight');
  assert(await page.locator('#photo-counter').textContent()==='3 / 3','Keyboard navigation works');
  await page.getByRole('button',{name:'Все фотографии',exact:false}).click();
  await page.getByRole('button',{name:'Закрыть альбом',exact:true}).click();
  assert(await page.locator('#album-dialog').evaluate(el=>!el.open),'Dialog closes');
  await page.emulateMedia({reducedMotion:'reduce'});
  await page.waitForFunction(()=>document.querySelector('#hero-video').paused);
  for(const width of [360,390,768,1024,1440]){
    await page.setViewportSize({width,height:900});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Public layout fits ${width}px`);
  }
  await page.goto(base+'/admin');
  for(const width of [360,390,768,1440]){
    await page.setViewportSize({width,height:900});
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Editor fits ${width}px`);
  }
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.close({runBeforeUnload:false});
  return 'PASS: editor login, three real uploads, cover selection, private draft, publication, HTTP calendar, gallery, keyboard, original and ZIP download, reduced motion, public/editor responsive layouts';
}
