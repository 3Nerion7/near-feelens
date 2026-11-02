'use strict';
(async function() {
  const byId = id => document.getElementById(id);
  const set = (id, text) => { byId(id).textContent = text; };
  const group = value => BigInt(value).toLocaleString('en-US');
  const shortToken = value => {
    const [whole, fraction=''] = value.split('.');
    return group(whole) + (fraction ? '.' + fraction.slice(0, 6) : '') + (fraction.length > 6 ? '…' : '');
  };
  const svgEl = (name, attributes, text) => {
    const node = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key,value] of Object.entries(attributes)) node.setAttribute(key, String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  };
  try {
    const response = await fetch('metrics.json', {cache:'no-store'});
    if (!response.ok) throw new Error('The local metrics file could not be read. Run the offline build.');
    const data = await response.json();
    if (data.schema !== 1 || data.data_kind !== 'real_public_rpc_snapshot' || !Array.isArray(data.blocks) || data.blocks.length !== 24) throw new Error('Unexpected snapshot schema. Rebuild from the verified raw sources.');
    const s = data.summary;
    const ratio = Number(s.gas_usage_ratio);
    if (!Number.isFinite(ratio) || ratio < 0 || ratio > 1) throw new Error('Invalid computed gas ratio.');
    set('block-count', s.block_count);
    set('window-range', s.from_utc.slice(11,19) + ' – ' + s.to_utc.slice(11,19) + ' UTC');
    set('window-seconds', s.elapsed_seconds + ' seconds · ' + s.from_utc.slice(0,10));
    set('gas-ratio', (ratio*100).toFixed(3) + '%');
    set('burnt', shortToken(s.reported_balance_burnt_near) + ' NEAR');
    byId('burnt').title = 'Exact reported aggregate: ' + s.reported_balance_burnt_near + ' NEAR';
    set('header-price', group(s.observed_header_gas_price_yocto_per_gas));
    set('pinned-hash', s.newest_hash);
    set('supply', s.newest_total_supply_near);
    set('protocol-capture', 'Protocol ' + data.protocol_version + ' · ' + data.capture_utc);
    set('observed-price-inline', group(s.observed_header_gas_price_yocto_per_gas));
    set('configured-price-inline', group(s.protocol_min_gas_price_field));
    byId('disagreement').hidden = !data.warnings.some(x => x.code === 'GAS_PRICE_CONTEXT');
    function drawChart(fullScale) {
      const peak = Math.max(...data.blocks.map(b => Number(b.gas_usage_ratio)));
      const axisMax = fullScale ? 1 : Math.max(.001, Math.ceil(peak*1000)/1000);
      const chart = svgEl('svg', {viewBox:'0 0 1000 250', 'aria-hidden':'true'});
      for (const p of [0,.25,.5,.75,1]) {
        const y = 215 - p*190;
        chart.append(svgEl('line', {x1:48,y1:y,x2:992,y2:y}));
        chart.append(svgEl('text', {x:0,y:y+4}, (p*axisMax*100).toFixed(axisMax < .01 ? 2 : 1) + '%'));
      }
      data.blocks.forEach((b,i) => {
        const r = Number(b.gas_usage_ratio);
        if (!Number.isFinite(r) || r < 0 || r > 1) throw new Error('Invalid observation ratio.');
        const bar = svgEl('rect', {x:54+i*39,y:215-(r/axisMax)*190,width:25,height:(r/axisMax)*190,rx:2,class:'bar'});
        bar.append(svgEl('title', {}, '#' + b.height + ' · ' + (r*100).toFixed(5) + '% · ' + b.utc));
        chart.append(bar);
      });
      byId('chart').replaceChildren(chart);
      set('axis-note','Vertical axis: 0–'+(axisMax*100).toFixed(2)+'% reported header-field ratio. '+(fullScale ? 'Full scale.' : 'Scaled to this small sample; the top is NOT 100%.'));
    }
    let fullScale = false;
    drawChart(false);
    byId('scale-toggle').addEventListener('click', () => {
      fullScale = !fullScale;
      byId('scale-toggle').setAttribute('aria-pressed', String(fullScale));
      set('scale-toggle', fullScale ? 'Use sample scale' : 'Use full 0–100% scale');
      drawChart(fullScale);
    });
    data.blocks.forEach(b => {
      const r = Number(b.gas_usage_ratio);
      if (!Number.isFinite(r) || r < 0 || r > 1) throw new Error('Invalid observation ratio.');
      const tr = document.createElement('tr');
      for (const text of ['#'+b.height,b.utc,(r*100).toFixed(6)+'%  ('+b.gas_used+' / '+b.included_gas_limit+')',b.reported_balance_burnt_near]) {
        const td = document.createElement('td'); td.textContent = text; tr.append(td);
      }
      byId('observations').append(tr);
    });
    set('oldest-label', '#' + s.oldest_height + ' · ' + s.from_utc.slice(11,19) + ' UTC');
    set('newest-label', '#' + s.newest_height + ' · ' + s.to_utc.slice(11,19) + ' UTC');
    function recalculate(event) {
      if (event) event.preventDefault();
      const error = byId('scenario-error');
      try {
        const args = [byId('horizon').value,byId('operations').value,byId('tgas').value,byId('state-bytes').value,
          byId('retention').value,s.observed_header_gas_price_yocto_per_gas,s.storage_amount_per_byte_yocto,byId('gas-multiplier').value];
        const result = FeeLensScenario.calculateLongTerm(...args);
        set('scenario-execution', group(result.gas_billing_proxy_near.split('.')[0])+(result.gas_billing_proxy_near.includes('.')?'.'+result.gas_billing_proxy_near.split('.')[1]:'') + ' NEAR');
        set('scenario-storage', shortToken(result.locked_storage_balance_near) + ' NEAR');
        set('scenario-append', shortToken(result.append_only_storage_balance_near) + ' NEAR');
        byId('scenario-storage').title = 'Exact: '+result.locked_storage_balance_near+' NEAR';
        byId('scenario-append').title = 'Exact: '+result.append_only_storage_balance_near+' NEAR';
        set('execution-formula', result.horizon_days+' days × '+group(result.operations_per_day)+' assumed operations/day × '+result.tgas_per_operation+' Tgas × '+group(result.model_gas_price_yocto_per_gas)+' yoctoNEAR/gas.');
        set('retained-formula', result.retained_days+' retained days × '+group(result.operations_per_day)+' operations/day × '+group(result.net_state_bytes_per_operation)+' net billable bytes/operation = '+group(result.retained_state_bytes)+' bytes.');
        const comparisons = ['30','365','1095'].map(days =>
          FeeLensScenario.calculateLongTerm(days,args[1],args[2],args[3],args[4],args[5],args[6],args[7]));
        byId('long-observations').replaceChildren();
        let maxBalance = 0n;
        comparisons.forEach(row => {
          const b = BigInt(row.append_only_storage_balance_yocto);
          if(b>maxBalance) maxBalance=b;
          const tr = document.createElement('tr');
          for(const value of [row.horizon_days,row.gas_billing_proxy_near,row.locked_storage_balance_near,row.append_only_storage_balance_near]) {
            const td = document.createElement('td'); td.textContent=value; tr.append(td);
          }
          byId('long-observations').append(tr);
        });
        const svg = svgEl('svg',{viewBox:'0 0 1000 250','aria-hidden':'true'});
        const denominator = maxBalance || 1n;
        for(let q=0;q<=4;q++) {
          const y=210-q*45;
          svg.append(svgEl('line',{x1:100,y1:y,x2:990,y2:y}));
          svg.append(svgEl('text',{x:0,y:y+4},shortToken(FeeLensScenario.tokenText(maxBalance*BigInt(q)/4n))));
        }
        comparisons.forEach((row,i) => {
          for(const [offset,field,cls] of [[0,'locked_storage_balance_yocto','retained-bar'],[65,'append_only_storage_balance_yocto','append-bar']]) {
            const value = BigInt(row[field]);
            const normalized = Number(value*1000000n/denominator)/1000000;
            const bar = svgEl('rect',{x:195+i*280+offset,y:210-normalized*180,width:52,height:normalized*180,rx:3,class:cls});
            bar.append(svgEl('title',{},row.horizon_days+' days · '+FeeLensScenario.tokenText(value)+' NEAR balance stock'));
            svg.append(bar);
          }
          svg.append(svgEl('text',{x:198+i*280,y:238},row.horizon_days+' days'));
        });
        byId('long-chart').replaceChildren(svg);
        error.hidden = true;
      } catch (problem) {
        error.textContent = problem.message; error.hidden = false;
        set('scenario-execution','—'); set('scenario-storage','—'); set('scenario-append','—');
        byId('long-chart').replaceChildren(); byId('long-observations').replaceChildren();
      }
    }
    byId('scenario-form').addEventListener('submit', recalculate);
    recalculate();
  } catch (problem) {
    const error = byId('load-error');
    error.textContent = problem.message + ' No scenario result should be relied on until the source data passes verification.';
    error.hidden = false;
  }
})();
