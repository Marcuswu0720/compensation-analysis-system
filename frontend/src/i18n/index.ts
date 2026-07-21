import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en';
import zh from './locales/zh';

export const LANG_STORAGE_KEY = 'lang';

const storedLang = localStorage.getItem(LANG_STORAGE_KEY);
const initialLang = storedLang === 'zh' || storedLang === 'en' ? storedLang : 'en';

i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    zh: { translation: zh },
  },
  lng: initialLang,
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
});

export function setLanguage(lang: 'en' | 'zh') {
  i18n.changeLanguage(lang);
  localStorage.setItem(LANG_STORAGE_KEY, lang);
}

export default i18n;
