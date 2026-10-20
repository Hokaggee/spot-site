async page => {
  const preview = await page.context().newPage();
  try {
    await preview.goto('http://127.0.0.1:8081/#events');
    await preview.locator('.event-poster').first().waitFor();
    await preview.evaluate(async () => {
      await document.fonts.ready;
      await Promise.all([...document.querySelectorAll('.event-poster')].map(image => {image.loading='eager'; return image.decode();}));
    });
    for (const width of [1440,768,601,390,320,1440]) {
      await preview.setViewportSize({width,height:900});
      await preview.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const error = await preview.evaluate(() => {
        const cards=[...document.querySelectorAll('.event')].map(node=>node.getBoundingClientRect());
        const columns=new Map();
        for(const card of cards){const x=Math.round(card.x); if(!columns.has(x))columns.set(x,[]);columns.get(x).push(card);}
        if(columns.size!==(innerWidth>600?2:1))return 'Wrong column count';
        for(const column of columns.values()){
          column.sort((a,b)=>a.top-b.top);
          for(let index=1;index<column.length;index++){
            const gap=column[index].top-column[index-1].bottom;
            if(Math.abs(gap-(innerWidth>600?24:20))>1.5)return `Unexpected gap ${gap}px`;
          }
        }
        if(document.documentElement.scrollWidth>innerWidth)return 'Horizontal overflow';
        for(let index=1;index<cards.length;index++)if(cards[index].top<cards[index-1].top-1)return 'Chronological reading order changed';
        return null;
      });
      if(error)throw new Error(`${width}px: ${error}`);
    }
    return 'PASS: two independent poster columns, consistent gaps, one mobile column, chronological order and live resize';
  } finally { await preview.close({runBeforeUnload:false}); }
}
