import tkinter as tk
r=tk.Tk(); r.title('ResearchFlow Selection Test'); r.geometry('650x280')
tk.Label(r,text='ResearchFlow AI cross-application test fixture').pack(anchor='w',padx=15,pady=10)
t=tk.Text(r,wrap='word',font=('Segoe UI',14),exportselection=False)
t.pack(fill='both',expand=True,padx=15,pady=10)
t.insert('1.0','We has tested this method and it work good.')
r.mainloop()
