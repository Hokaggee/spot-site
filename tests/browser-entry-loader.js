async page => {
  const preview = await page.context().newPage();
  const base='http://127.0.0.1:8081';
  const reset=async()=>{await preview.goto(base+'/assets/loader-preview.html');await preview.evaluate(()=>{localStorage.removeItem('spot:intro:assembly:v1');localStorage.removeItem('spot:intro:assembly:v1:mobile');});};
  try {
    await preview.emulateMedia({reducedMotion:'no-preference'});
    await reset();
    await preview.evaluate(()=>{
      localStorage.setItem('spot:intro:assembly:v1','seen');
      localStorage.setItem('spot:intro:assembly:v1:mobile','seen');
    });
    await preview.goto(base+'/',{waitUntil:'domcontentloaded'});
    await preview.waitForFunction(()=>document.documentElement.classList.contains('entry-pending'),null,{timeout:1500});
    if(await preview.locator('.entry-piece').count()!==4)throw new Error('Selected assembly animation is missing');
    if(await preview.locator('#entry-loader button').count())throw new Error('Loader still has a skip button');
    if(await preview.evaluate(()=>document.documentElement.classList.contains('entry-return')))throw new Error('Old visit markers still shorten the animation');
    await preview.locator('#entry-loader').waitFor({state:'hidden',timeout:6000});
    await preview.waitForFunction(()=>!document.querySelector('#hero-video').paused);
    if(await preview.locator('main').evaluate(main=>main.inert))throw new Error('Homepage stays inert after intro');
    await preview.reload({waitUntil:'domcontentloaded'});
    await preview.waitForFunction(()=>document.documentElement.classList.contains('entry-running'),null,{timeout:2000});
    if(await preview.locator('.entry-piece').first().evaluate(node=>getComputedStyle(node).animationName)!=='entry-assemble')throw new Error('Reload does not replay the full assembly');
    await preview.locator('#entry-loader').waitFor({state:'hidden',timeout:6000});
    await reset();
    await preview.goto(base+'/',{waitUntil:'domcontentloaded'});
    await preview.keyboard.press('Escape');
    await preview.locator('#entry-loader').waitFor({state:'hidden',timeout:1000});
    await preview.goto(base+'/#events',{waitUntil:'domcontentloaded'});
    await preview.reload({waitUntil:'domcontentloaded'});
    await preview.keyboard.press('Escape');
    await preview.emulateMedia({reducedMotion:'reduce'});
    await preview.reload();
    if(await preview.evaluate(()=>document.documentElement.classList.contains('entry-pending')))throw new Error('Reduced motion still shows the intro');
    await preview.emulateMedia({reducedMotion:'no-preference'});
    await preview.goto(base+'/?preview=loader');
    if(await preview.evaluate(()=>document.documentElement.classList.contains('entry-pending')))throw new Error('Intro plays twice inside the comparison demo');
    await preview.route('**/assets/entry-loader.js',route=>route.fulfill({contentType:'text/javascript',body:''}));
    await preview.goto(base+'/');
    if(await preview.locator('#entry-loader').isVisible())throw new Error('Failed loader script hides the website');
    return 'PASS: full assembly without a skip button, every reload, video, Escape, reduced motion, preview bypass and script failure';
  } finally {await preview.close({runBeforeUnload:false});}
}
