async page => {
  const preview = await page.context().newPage();
  try {
    const response = await preview.goto('http://127.0.0.1:8081/assets/loader-preview.html');
    if (response.status() !== 200) throw new Error('Loader preview page is unavailable');
    for (let number=1; number<=4; number++) {
      await preview.getByRole('button',{name:`Смотреть вариант ${number}`,exact:true}).click();
      await preview.locator('#loader-overlay:not([hidden])').waitFor();
      await preview.locator('#loader-overlay').waitFor({state:'hidden',timeout:8000});
      if(await preview.locator('#preview-frame').getAttribute('src')!=='/?preview=loader')throw new Error('Transition does not reveal the real homepage');
      await preview.frameLocator('#preview-frame').getByRole('heading',{name:'СПОТ',exact:true}).waitFor({timeout:5000});
      await preview.getByRole('button',{name:'Повторить анимацию',exact:true}).click();
      await preview.locator('#loader-overlay:not([hidden])').waitFor();
      await preview.getByRole('button',{name:'Пропустить анимацию',exact:true}).click();
      await preview.locator('#loader-overlay').waitFor({state:'hidden'});
      await preview.frameLocator('#preview-frame').locator('body').press('Escape');
      if(await preview.locator('#preview-dialog').evaluate(dialog=>dialog.open))throw new Error('Escape did not close the preview');
    }
    for(const width of [320,390,768,1440]){
      await preview.setViewportSize({width,height:900});
      if(!await preview.evaluate(()=>document.documentElement.scrollWidth<=innerWidth))throw new Error(`Overflow at ${width}px`);
    }
    await preview.emulateMedia({reducedMotion:'reduce'});
    await preview.getByRole('button',{name:'Смотреть вариант 1',exact:true}).click();
    await preview.locator('#loader-overlay').waitFor({state:'hidden',timeout:1500});
    return 'PASS: four complete animations, real homepage reveal, replay, skip, Escape, responsive gallery and reduced motion';
  } finally { await preview.close({runBeforeUnload:false}); }
}
