const petEl = document.getElementById('pet');
const bubble = document.getElementById('bubble');

const PHRASES = ['喵~', '摸摸我呀', '今天也要元气满满哦', '别忘了喝水', '来陪我玩嘛', 'zzZ...'];

let mouseDown = false;
let didDrag = false;
let downPoint = null;
let happyTimeout = null;
let bubbleTimeout = null;

function setState(state) {
  petEl.dataset.state = state;
}

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function showBubble(text) {
  clearTimeout(bubbleTimeout);
  bubble.textContent = text;
  bubble.classList.add('visible');
  bubbleTimeout = setTimeout(() => bubble.classList.remove('visible'), 2000);
}

function reactToClick() {
  clearTimeout(happyTimeout);
  setState('happy');
  showBubble(PHRASES[Math.floor(Math.random() * PHRASES.length)]);
  happyTimeout = setTimeout(() => setState('idle'), 1000);
}

petEl.addEventListener('mousedown', (event) => {
  if (event.button !== 0) return;
  mouseDown = true;
  didDrag = false;
  downPoint = { x: event.screenX, y: event.screenY };
  window.pet.dragStart();
  setState('dragging');
});

document.addEventListener('mousemove', (event) => {
  if (!mouseDown || !downPoint) return;
  if (!didDrag && distance({ x: event.screenX, y: event.screenY }, downPoint) > 4) {
    didDrag = true;
  }
});

document.addEventListener('mouseup', () => {
  if (!mouseDown) return;
  mouseDown = false;
  window.pet.dragEnd();
  downPoint = null;

  if (didDrag) {
    setState('idle');
  } else {
    reactToClick();
  }
});

petEl.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  window.pet.showContextMenu();
});

window.pet.onState((payload) => {
  switch (payload.action) {
    case 'walk':
      petEl.dataset.facing = payload.facingLeft ? 'left' : 'right';
      setState('walk');
      break;
    case 'idle':
      setState('idle');
      break;
    case 'set-skin':
      petEl.dataset.skin = payload.skin;
      break;
    default:
      break;
  }
});
