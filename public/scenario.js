(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FeeLensScenario = factory();
})(globalThis, function() {
  'use strict';
  const YOCTO = 10n ** 24n;
  function uint(value, max, name) {
    if (typeof value !== 'string' || !/^(0|[1-9][0-9]*)$/.test(value)) throw new Error(name + ': use a whole nonnegative number.');
    const result = BigInt(value);
    if (max !== null && result > max) throw new Error(name + ': value exceeds the declared limit.');
    return result;
  }
  function tokenText(value) {
    const whole = value / YOCTO;
    const fraction = (value % YOCTO).toString().padStart(24, '0').replace(/0+$/, '');
    return whole.toString() + (fraction ? '.' + fraction : '');
  }
  function calculate(operations, tgas, bytes, price, byteCost) {
    const ops = uint(operations, 1000000n, 'Operations');
    const storage = uint(bytes, 1000000000n, 'Stored bytes');
    const gasPrice = uint(price, null, 'Gas price');
    const storageCost = uint(byteCost, null, 'Storage parameter');
    if (!gasPrice || !storageCost) throw new Error('Source cost parameters must be positive.');
    if (typeof tgas !== 'string' || !/^(0|[1-9][0-9]{0,2})(\.[0-9]{1,3})?$/.test(tgas)) throw new Error('Tgas: use 0.001–300 with at most three decimals.');
    const parts = tgas.split('.');
    const milli = BigInt(parts[0]) * 1000n + BigInt((parts[1] || '').padEnd(3, '0'));
    if (milli < 1n || milli > 300000n) throw new Error('Tgas must be between 0.001 and 300.');
    const gas = ops * milli * (10n ** 9n);
    const execution = gas * gasPrice;
    const stored = storage * storageCost;
    return {kind:'hypothetical', scope:'static observed price times assumed consumed gas; not a transaction quote', operations:ops.toString(), tgas_per_operation:tgas, storage_bytes:storage.toString(),
      gas_units:gas.toString(), gas_price_yocto_per_gas:gasPrice.toString(), execution_cost_yocto:execution.toString(),
      execution_cost_near:tokenText(execution), storage_balance_yocto:stored.toString(), storage_balance_near:tokenText(stored)};
  }
  function calculateLongTerm(days, dailyOps, tgas, stateBytes, retention, price, byteCost, multiplier='1') {
    const horizon = uint(days,3650n,'Horizon days');
    const daily = uint(dailyOps,1000000n,'Operations per day');
    const netBytes = uint(stateBytes,1000000n,'Net billable state bytes');
    const retained = uint(retention,3650n,'Retention days');
    const anchor = uint(price,null,'Header gas price');
    const storagePrice = uint(byteCost,null,'Storage parameter');
    if (!horizon || !retained) throw new Error('Horizon and retention must each be 1–3650 days.');
    if (typeof multiplier !== 'string' || !['1','10'].includes(multiplier)) throw new Error('Choose the explicit 1× or 10× gas-price sensitivity.');
    const modelPrice = anchor * BigInt(multiplier);
    const oneDay = calculate(daily.toString(),tgas,'0',modelPrice.toString(),storagePrice.toString());
    const gas = BigInt(oneDay.gas_units) * horizon;
    const proxy = BigInt(oneDay.execution_cost_yocto) * horizon;
    const retainedDays = retained < horizon ? retained : horizon;
    const retainedBytes = retainedDays * daily * netBytes;
    const appendBytes = horizon * daily * netBytes;
    const locked = retainedBytes * storagePrice;
    const append = appendBytes * storagePrice;
    return {kind:'hypothetical_long_term',horizon_days:horizon.toString(),operations_per_day:daily.toString(),
      tgas_per_operation:tgas,net_state_bytes_per_operation:netBytes.toString(),retention_days:retained.toString(),retained_days:retainedDays.toString(),
      gas_price_multiplier:multiplier,static_header_gas_price_yocto_per_gas:anchor.toString(),model_gas_price_yocto_per_gas:modelPrice.toString(),
      storage_yocto_per_byte:storagePrice.toString(),cumulative_consumed_gas_units:gas.toString(),gas_billing_proxy_yocto:proxy.toString(),gas_billing_proxy_near:tokenText(proxy),
      retained_state_bytes:retainedBytes.toString(),append_only_state_bytes:appendBytes.toString(),locked_storage_balance_yocto:locked.toString(),locked_storage_balance_near:tokenText(locked),
      append_only_storage_balance_yocto:append.toString(),append_only_storage_balance_near:tokenText(append),balance_difference_yocto:(append-locked).toString(),balance_difference_near:tokenText(append-locked)};
  }
  return Object.freeze({calculate, calculateLongTerm, tokenText});
});
