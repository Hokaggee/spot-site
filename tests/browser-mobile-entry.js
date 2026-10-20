async page => {
  const preview=await page.context().newPage();
  try {
    await preview.emulateMedia({reducedMotion:'no-preference'});
    await preview.goto('http://127.0.0.1:8081/assets/loader-preview.html');
    await preview.evaluate(()=>{
      localStorage.setItem('spot:intro:assembly:v1','seen');
      localStorage.removeItem('spot:intro:assembly:v1:mobile');
    });
    await preview.setViewportSize({width:390,height:844});
    await preview.goto('http://127.0.0.1:8081/',{waitUntil:'domcontentloaded'});
    if(await preview.evaluate(()=>document.documentElement.classList.contains('entry-return')))throw new Error('Desktop visit suppresses the full mobile animation');
    await preview.waitForFunction(()=>document.documentElement.classList.contains('entry-running'),null,{timeout:2000});
    const fits=await preview.locator('.entry-logo').evaluate(node=>{
      const rect=node.getBoundingClientRect();
      return rect.width>250 && rect.left>=0 && rect.right<=innerWidth && getComputedStyle(node.firstElementChild).animationName==='entry-assemble';
    });
    if(!fits)throw new Error('Mobile logo does not fit or animate');
    await preview.locator('#entry-loader').waitFor({state:'hidden',timeout:6000});
    await preview.waitForFunction(()=>!document.querySelector('#hero-video').paused);
    await preview.reload({waitUntil:'domcontentloaded'});
    await preview.waitForFunction(()=>document.documentElement.classList.contains('entry-running'),null,{timeout:2000});
    if(await preview.locator('.entry-piece').first().evaluate(node=>getComputedStyle(node).animationName)!=='entry-assemble')throw new Error('Mobile reload should replay the full assembly');
    await preview.locator('#entry-loader').waitFor({state:'hidden',timeout:6000});
    return 'PASS: full mobile intro on first load and reload, logo fits and animates, video resumes';
  } finally {await preview.close({runBeforeUnload:false});}
}
