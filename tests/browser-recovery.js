async page => {
  page = await page.context().newPage();
  const base='http://127.0.0.1:8082', failures=[];
  async function check(name,run){try{await run();}catch(error){failures.push(name+': '+error.message);}}
  await check('Reduced-motion manual pause',async()=>{
    await page.emulateMedia({reducedMotion:'reduce'});await page.goto(base+'/');
    await page.waitForFunction(()=>document.querySelector('#hero-video').paused);
    await page.locator('.video-toggle').click();await page.waitForFunction(()=>!document.querySelector('#hero-video').paused);
    await page.locator('.video-toggle').click();
    await page.waitForFunction(()=>document.querySelector('#hero-video').paused,null,{timeout:1500});
  });
  await check('Initial calendar refresh',async()=>{
    let calls=0;
    await page.route('**/api/events',async route=>{calls++;await route.fulfill({json:calls===1?{events:[],updated_at:null}:{events:[{title:'Проверка обновления',starts_at:'2026-12-01T20:00:00+09:00',poster:'',url:'https://blagoveshensk.qtickets.events/123-test',price:'от 100 ₽',category:'Концерт'}],updated_at:new Date().toISOString()}});});
    await page.goto(base+'/');await page.locator('.event').first().waitFor({timeout:6000});await page.unroute('**/api/events');
  });
  await page.unroute('**/api/events');
  await check('Upload resumes without duplicates after login',async()=>{
    await page.goto(base+'/admin');await page.waitForFunction(()=>document.querySelector('#initial-status').hidden);
    if(await page.locator('#login-panel').isVisible()){await page.getByLabel('Логин',{exact:true}).fill('admin');await page.getByLabel('Пароль',{exact:true}).fill('spot-qa-only-password');await page.getByRole('button',{name:'Войти',exact:true}).click();}
    await page.locator('#workspace').waitFor({state:'visible'});await page.locator('#new-album').click();
    await page.getByLabel('Название вечеринки').fill('Восстановление загрузки');await page.getByLabel('Дата вечеринки').fill('2026-10-16');
    let uploads=0;
    await page.route('**/api/admin/albums/*/photos',async route=>{if(route.request().method()==='POST'&&++uploads===2)await route.fulfill({status:401,json:{error:'Войдите снова. Уже загруженные фотографии сохранены в черновике.'}});else await route.continue();});
    await page.locator('#photo-input').setInputFiles(['/Users/ivan/Downloads/spot-site/assets/moment-01.png','/Users/ivan/Downloads/spot-site/assets/moment-02.png','/Users/ivan/Downloads/spot-site/assets/moment-03.png']);
    await page.locator('#login-panel').waitFor({state:'visible'});
    await page.waitForFunction(()=>!document.querySelector('#login-submit').disabled&&!document.querySelector('#new-album').disabled);
    await page.getByLabel('Логин',{exact:true}).fill('admin');await page.getByLabel('Пароль',{exact:true}).fill('spot-qa-only-password');await page.locator('#login-submit').click();
    await page.waitForFunction(()=>document.querySelectorAll('.cover-choice').length===3&&!document.querySelector('#publish').disabled,null,{timeout:7000});
    if(await page.locator('.cover-choice').count()!==3)throw new Error('Expected exactly three photos after retry');
    await page.unroute('**/api/admin/albums/*/photos');
  });
  await page.unroute('**/api/admin/albums/*/photos');await page.emulateMedia({reducedMotion:'no-preference'});
  await page.close({runBeforeUnload:false});
  return failures.length?{failures}:'PASS: manual pause with reduced motion, initial calendar polling, expired upload resumes exactly once';
}
