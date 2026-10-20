async page => {
  const preview=await page.context().newPage();
  const assert=(value,message)=>{if(!value)throw new Error(message);};
  try{
    await preview.goto('http://127.0.0.1:8081/');
    await preview.evaluate(()=>document.fonts.ready);
    await preview.locator('.event').first().waitFor();
    for(const width of [320,360,390,600,768,1024,1440]){
      await preview.setViewportSize({width,height:900});
      assert(await preview.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`No overflow at ${width}px`);
      const insta=preview.locator('.header-socials a').filter({hasText:'Instagram'});
      assert(await insta.isVisible(),`Instagram is visible at ${width}px`);
      assert(await insta.getAttribute('href')==='https://www.instagram.com/spot.blg/','Instagram goes to the club account');
      assert(await preview.evaluate(()=>{
        const brand=document.querySelector('.header>.brand').getBoundingClientRect();
        const socials=document.querySelector('.header-socials').getBoundingClientRect();
        const ticket=document.querySelector('.ticket-button');
        return brand.right<=socials.left&&socials.right<=innerWidth&&ticket.scrollWidth<=ticket.clientWidth+1;
      }),`Header and ticket content fit without overlap at ${width}px`);
      const buttons=await preview.locator('.event .button').evaluateAll(nodes=>nodes.map(n=>n.getBoundingClientRect().height));
      assert(buttons.every(height=>height>=48),`Ticket buttons are at least 48px tall at ${width}px`);
      const route=preview.getByRole('link',{name:'Построить маршрут в 2ГИС',exact:true});
      assert(await route.getAttribute('href')==='https://2gis.ru/blagoveshensk/firm/70000001110675808','Route opens the confirmed 2GIS destination');
    }
    const faces=await preview.evaluate(async()=>{const fonts=await document.fonts.load('700 40px Oswald','АФИША СПОТ');return fonts.length>0&&fonts.every(font=>font.status==='loaded');});
    assert(faces,'Local Cyrillic display font loaded');
    await preview.getByRole('link',{name:'Смотреть афишу',exact:true}).click();
    assert(new URL(preview.url()).hash==='#events','Ticket CTA navigates to events');
    return 'PASS: local Cyrillic font, social links, 2GIS, ticket navigation, 48px buttons and seven viewport widths without header overlap';
  }finally{await preview.close({runBeforeUnload:false});}
}
