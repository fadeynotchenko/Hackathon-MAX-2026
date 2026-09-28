import '@testing-library/jest-dom/vitest';

// jsdom не реализует matchMedia, а провайдер MAX UI читает через него
// системную тему.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

// Прокрутку к ошибкам формы и к тексту шаблона jsdom тоже не умеет.
window.scrollTo = () => undefined;
Element.prototype.scrollIntoView = () => undefined;
