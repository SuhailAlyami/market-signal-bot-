"""Visible local credential entry. No token/chat value is printed or committed."""
import tkinter as tk
from tkinter import messagebox
import importlib
import telegram_signal_delivery


def main():
    root=tk.Tk();root.title('Suhail Hunter — Secure Telegram setup')
    root.geometry('520x250')
    tk.Label(root,text='أدخل بيانات البوت هنا فقط؛ ستُشفّر لحساب Windows الحالي.').pack(pady=12)
    tk.Label(root,text='Bot token').pack()
    token=tk.Entry(root,show='*',width=65);token.pack()
    tk.Label(root,text='Chat ID (ابدأ محادثة البوت أولاً بالضغط على Start)').pack(pady=7)
    chat=tk.Entry(root,width=40);chat.pack()
    def save():
        try:importlib.reload(telegram_signal_delivery).save_credentials(token.get(),chat.get())
        except ValueError:
            messagebox.showerror('لم يُحفظ','تحقق من تنسيق رمز البوت ومعرّف المحادثة.');return
        except Exception:
            messagebox.showerror('لم يُحفظ','تعذر إنشاء مخزن أسرار خاص؛ لم تعرض القيم.');return
        token.delete(0,'end');chat.delete(0,'end')
        messagebox.showinfo('تم الحفظ','حُفظت البيانات مشفّرة خارج المشروع. سيرسل الرصد رسالة تحقق واحدة فقط.')
        root.destroy()
    tk.Button(root,text='حفظ آمن وتفعيل تليجرام',command=save).pack(pady=15)
    root.mainloop()


if __name__=='__main__':main()
