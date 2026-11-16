"use client";

// Lightweight English/Thai dictionary. Navigation, POS, kitchen and common
// actions are translated; strings without a Thai entry fall back to English.

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type Language = "en" | "th";

const th: Record<string, string> = {
  Dashboard: "แดชบอร์ด",
  POS: "ขายหน้าร้าน",
  Orders: "ออเดอร์",
  Tables: "โต๊ะ",
  Menu: "เมนู",
  Recipes: "สูตรอาหาร",
  Inventory: "คลังวัตถุดิบ",
  Suppliers: "ผู้จำหน่าย",
  "Purchase Orders": "ใบสั่งซื้อ",
  Customers: "ลูกค้า",
  "Kitchen Display": "จอครัว",
  Analytics: "วิเคราะห์",
  Forecasting: "พยากรณ์",
  "AI Assistant": "ผู้ช่วย AI",
  Reports: "รายงาน",
  "User Management": "จัดการผู้ใช้",
  Settings: "ตั้งค่า",
  Administration: "ผู้ดูแลระบบ",
  "Sign in": "เข้าสู่ระบบ",
  "Sign out": "ออกจากระบบ",
  Email: "อีเมล",
  Password: "รหัสผ่าน",
  Search: "ค้นหา",
  "Search products": "ค้นหาสินค้า",
  All: "ทั้งหมด",
  Cart: "ตะกร้า",
  "Dine-in": "ทานที่ร้าน",
  Takeaway: "กลับบ้าน",
  Table: "โต๊ะ",
  Customer: "ลูกค้า",
  Guest: "ลูกค้าทั่วไป",
  Subtotal: "ยอดรวม",
  Discount: "ส่วนลด",
  "Service charge": "ค่าบริการ",
  Tax: "ภาษี",
  Total: "ยอดสุทธิ",
  "Send to kitchen": "ส่งเข้าครัว",
  "Confirm & pay": "ยืนยันและชำระเงิน",
  Pay: "ชำระเงิน",
  "Save draft": "บันทึกร่าง",
  Clear: "ล้าง",
  Notes: "หมายเหตุ",
  New: "ใหม่",
  Preparing: "กำลังทำ",
  Ready: "พร้อมเสิร์ฟ",
  Completed: "เสร็จสิ้น",
  "Start preparing": "เริ่มทำ",
  "Mark ready": "พร้อมเสิร์ฟ",
  "Mark completed": "เสร็จสิ้น",
  Save: "บันทึก",
  Cancel: "ยกเลิก",
  Close: "ปิด",
  Add: "เพิ่ม",
  Edit: "แก้ไข",
  Delete: "ลบ",
  Loading: "กำลังโหลด",
  "Print receipt": "พิมพ์ใบเสร็จ",
  "Today's sales": "ยอดขายวันนี้",
  "Net sales": "ยอดขายสุทธิ",
  Language: "ภาษา",
  Restaurant: "ร้านอาหาร",
  "Empty cart": "ยังไม่มีสินค้าในตะกร้า",
  Available: "ว่าง",
  Occupied: "มีลูกค้า",
  Reserved: "จองแล้ว",
  Cleaning: "ทำความสะอาด",
  // Sign-in and password pages
  "Welcome back": "ยินดีต้อนรับกลับ",
  "Sign in to your restaurant workspace.": "เข้าสู่ระบบเพื่อจัดการร้านของคุณ",
  "Show password": "แสดงรหัสผ่าน",
  "Hide password": "ซ่อนรหัสผ่าน",
  "Caps Lock is on": "เปิด Caps Lock อยู่",
  "Keep me signed in": "จดจำการเข้าสู่ระบบ",
  "Forgot password?": "ลืมรหัสผ่าน?",
  "Signing in…": "กำลังเข้าสู่ระบบ…",
  "Signed in": "เข้าสู่ระบบแล้ว",
  "Email or password is incorrect": "อีเมลหรือรหัสผ่านไม่ถูกต้อง",
  "Check both and try again. Passwords are case-sensitive.": "ตรวจสอบอีกครั้ง รหัสผ่านแยกตัวพิมพ์เล็กและใหญ่",
  "Too many sign-in attempts": "พยายามเข้าสู่ระบบหลายครั้งเกินไป",
  "Sign-in is paused for this account. Try again in": "ระงับการเข้าสู่ระบบชั่วคราว ลองใหม่ในอีก",
  "You can try again now.": "ลองเข้าสู่ระบบอีกครั้งได้แล้ว",
  "Can't reach SmartPOS": "ติดต่อเซิร์ฟเวอร์ไม่ได้",
  "Check your connection and try again.": "ตรวจสอบการเชื่อมต่อแล้วลองอีกครั้ง",
  "Sign-in failed": "เข้าสู่ระบบไม่สำเร็จ",
  "Your session ended": "เซสชันหมดอายุ",
  "Sign in again to continue where you left off.": "เข้าสู่ระบบอีกครั้งเพื่อทำงานต่อ",
  "You're signed out": "ออกจากระบบแล้ว",
  "Sign in again whenever you're ready.": "เข้าสู่ระบบได้ทุกเมื่อที่พร้อม",
  "Password updated": "เปลี่ยนรหัสผ่านแล้ว",
  "Sign in with your new password.": "เข้าสู่ระบบด้วยรหัสผ่านใหม่",
  "Try the live demo": "ทดลองใช้งานเดโม",
  "No account needed": "ไม่ต้องสมัครสมาชิก",
  "or sign in with email": "หรือเข้าสู่ระบบด้วยอีเมล",
  "Enter your email address": "กรอกอีเมล",
  "Enter a valid email address": "กรอกอีเมลให้ถูกต้อง",
  "Enter your password": "กรอกรหัสผ่าน",
  "You're already signed in": "คุณเข้าสู่ระบบอยู่แล้ว",
  Continue: "ดำเนินการต่อ",
  "Use another account": "ใช้บัญชีอื่น",
  "Demo accounts": "บัญชีทดลอง",
  "Protected by encrypted sessions and role-based access": "ปกป้องด้วยเซสชันเข้ารหัสและสิทธิ์ตามบทบาท",
  "Switch to dark theme": "เปลี่ยนเป็นธีมมืด",
  "Switch to light theme": "เปลี่ยนเป็นธีมสว่าง",
  "Reset your password": "รีเซ็ตรหัสผ่าน",
  "Enter your account email and we'll send you a link to choose a new password.":
    "กรอกอีเมลของบัญชี แล้วเราจะส่งลิงก์สำหรับตั้งรหัสผ่านใหม่ให้",
  "Send reset link": "ส่งลิงก์รีเซ็ต",
  "Back to sign in": "กลับไปหน้าเข้าสู่ระบบ",
  "Check your inbox": "ตรวจสอบอีเมลของคุณ",
  "Choose a new password": "ตั้งรหัสผ่านใหม่",
  "New password": "รหัสผ่านใหม่",
  "Confirm password": "ยืนยันรหัสผ่าน",
  "Update password": "เปลี่ยนรหัสผ่าน",
  "The passwords do not match.": "รหัสผ่านไม่ตรงกัน",
  "Restaurant point of sale": "ระบบขายหน้าร้านสำหรับร้านอาหาร",
  "Run your restaurant from order to reorder.": "บริหารร้านตั้งแต่รับออเดอร์ จนถึงสั่งวัตถุดิบเข้าร้าน",
  "Sell, cook, count stock and plan purchasing in one place, with every number traceable to the orders behind it.":
    "ขาย ทำอาหาร นับสต็อก และวางแผนสั่งซื้อในที่เดียว ทุกตัวเลขย้อนกลับไปดูออเดอร์ต้นทางได้",
  Order: "ออเดอร์",
  Kitchen: "ครัว",
  Stock: "สต็อก",
  Forecast: "พยากรณ์",
  Reorder: "สั่งซื้อ",
  "Live across every screen": "อัปเดตสดทุกหน้าจอ",
  "Orders reach the kitchen, tables and dashboard in about a second.": "ออเดอร์ถึงครัว โต๊ะ และแดชบอร์ดในราวหนึ่งวินาที",
  "Forecasts you can check": "พยากรณ์ที่ตรวจสอบได้",
  "Backtested demand models and reorder suggestions with their maths.": "โมเดลพยากรณ์ที่ทดสอบย้อนหลัง พร้อมคำแนะนำการสั่งซื้อและที่มาของตัวเลข",
  "Explainable insights": "ข้อมูลเชิงลึกที่อธิบายได้",
  "Stock-out risk, best sellers and add-ons from your own sales.": "ความเสี่ยงของหมด เมนูขายดี และเมนูแนะนำ จากยอดขายของร้านเอง",
  "This link can't be used": "ใช้ลิงก์นี้ไม่ได้",
  "You'll use it to sign in on every device.": "ใช้รหัสนี้เข้าสู่ระบบในทุกอุปกรณ์",
};

const dictionaries: Record<Language, Record<string, string>> = { en: {}, th };
const STORAGE_KEY = "smartpos.language";

interface I18nValue {
  language: Language;
  setLanguage: (language: Language) => void;
  t: (text: string) => string;
}

const I18nContext = createContext<I18nValue>({ language: "en", setLanguage: () => {}, t: (s) => s });

export function I18nProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>("en");

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- hydrate the saved preference once
      if (stored === "th" || stored === "en") setLanguageState(stored);
    } catch {
      // ignore unavailable storage
    }
  }, []);

  useEffect(() => {
    document.documentElement.lang = language;
  }, [language]);

  const setLanguage = useCallback((next: Language) => {
    setLanguageState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore
    }
  }, []);

  const value = useMemo<I18nValue>(
    () => ({ language, setLanguage, t: (text) => dictionaries[language][text] ?? text }),
    [language, setLanguage],
  );
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  return useContext(I18nContext);
}

export function translate(language: Language, text: string) {
  return dictionaries[language][text] ?? text;
}
