// Тема до первой отрисовки: сохранённый выбор, иначе — настройка системы. Подключается в <head> без defer.
(function () {
  var saved = null;
  try { saved = localStorage.getItem('snc-theme'); } catch (error) { /* без хранилища */ }
  var system = window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  document.documentElement.dataset.theme = saved === 'light' || saved === 'dark' ? saved : system;
  window.sncSavedTheme = function () { return document.documentElement.dataset.theme; };
})();
