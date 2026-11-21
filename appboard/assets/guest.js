(() => {
  const send = (action, value = '') => parent.postMessage({type:'appboard:command', action, value}, '*');
  const listeners = new Set();
  let state = Object.freeze({url:'', title:'', canGoBack:false, canGoForward:false, loading:false});
  window.AppBoard = Object.freeze({browser: Object.freeze({
    navigate: url => send('navigate', String(url)),
    back: () => send('back'),
    forward: () => send('forward'),
    reload: () => send('reload'),
    get state() { return state; },
    subscribe(fn) { listeners.add(fn); fn(state); return () => listeners.delete(fn); }
  })});
  addEventListener('message', e => {
    if (e.source !== parent || e.data?.type !== 'appboard:state') return;
    state = Object.freeze(e.data.state);
    for (const fn of listeners) fn(state);
  });
  send('state');
})();
