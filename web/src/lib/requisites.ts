// Проверка реквизитов в браузере — те же правила и тексты, что у ядра
// (core.domain.documents.normalize). Сервер всё равно проверяет сам; здесь — чтобы
// неверный ИНН был виден, как только человек ушёл с поля, а не после «Сохранить»:
// на проде за месяц 11 карточек организаций вернулись с ошибками разом.
import type { FieldType } from '@/api/client';

const digitsOf = (value: string) => value.replace(/\D/g, '');

function checksum(digits: string, weights: readonly number[]): number {
  return (
    (weights.reduce((sum, weight, index) => sum + Number(digits[index]) * weight, 0) % 11) % 10
  );
}

export function innValid(value: string): boolean {
  const digits = digitsOf(value);
  if (digits.length === 10) {
    return checksum(digits, [2, 4, 10, 3, 5, 9, 4, 6, 8]) === Number(digits[9]);
  }
  if (digits.length === 12) {
    return (
      checksum(digits, [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === Number(digits[10]) &&
      checksum(digits, [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === Number(digits[11])
    );
  }
  return false;
}

// ОГРН — 13 цифр с контролем по модулю 11, ОГРНИП — 15 по модулю 13.
export function ogrnValid(value: string): boolean {
  const digits = digitsOf(value);
  if (digits.length === 13) return (Number(digits.slice(0, 12)) % 11) % 10 === Number(digits[12]);
  if (digits.length === 15) return (Number(digits.slice(0, 14)) % 13) % 10 === Number(digits[14]);
  return false;
}

const KPP = /^[0-9]{4}[0-9A-Z]{2}[0-9]{3}$/;

// Что не так со значением реквизита, или null. Пустое — не ошибка: обязательность
// проверяет форма целиком.
export function requisiteProblem(type: FieldType, value: string): string | null {
  if (!value.trim()) return null;
  switch (type) {
    case 'inn':
      return innValid(value) ? null : 'ИНН не проходит проверку';
    case 'kpp':
      return KPP.test(value.toUpperCase().replace(/[^0-9A-Z]/g, '')) ? null : 'КПП из 9 цифр';
    case 'ogrn':
      return ogrnValid(value) ? null : 'ОГРН не проходит проверку';
    case 'bic': {
      const digits = digitsOf(value);
      if (digits.length !== 9) return 'БИК из 9 цифр';
      return digits.startsWith('04') ? null : 'БИК банка начинается с 04';
    }
    case 'account':
      return digitsOf(value).length === 20 ? null : 'Счёт из 20 цифр';
    default:
      return null;
  }
}
