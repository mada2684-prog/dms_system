import os
import sys
import urllib.parse
import win32com.client
import requests

# إعدادات السيرفر الرئيسي لشركة شمال القاهرة
SERVER_URL = "http://127.0.0.1:5001"

def scan_and_upload(letter_id):
    print(f"[+] جاري الاتصال بالماسح الضوئي للمكاتبة رقم #{letter_id}...")
    try:
        # الاتصال بمدير أجهزة الويندوز المدمج WIA
        wia = win32com.client.Dispatch("WIA.CommonDialog")
        
        # فتح شاشة الويندوز الرسمية لاختيار السكنر وبدء السحب (تظهر للموظف لاختيار دقة الألوان والمسح)
        image = wia.ShowAcquireImage(
            DeviceType=1,       # 1 تعني Scanner
            Intent=2,           # 2 تعني Grayscale/Document Text (أفضل للمستندات)
            BiasIntent=65536,   # جودة معتمدة للمستندات الإدارية
            FormatID="{B96B3CAF-0728-11D3-9D7B-0000F81EF32E}" # صيغة PNG / JPEG عالية الجودة
        )
        
        if image:
            # حفظ الصورة مؤقتاً على جهاز الموظف
            temp_path = "C:\\temp_scan.png"
            if os.path.exists(temp_path):
                os.remove(temp_path)
            
            image.SaveFile(temp_path)
            print("[+] تم السحب الضوئي بنجاح. جاري الرفع التلقائي للسيرفر الرئيسي...")
            
            # إرسال الملف خلف الكواليس إلى سيرفر الـ Flask دون أي عناء من الموظف
            upload_url = f"{SERVER_URL}/api/upload_scanner_file/{letter_id}"
            with open(temp_path, 'rb') as f:
                files = {'file': (f'scan_{letter_id}.png', f, 'image/png')}
                response = requests.post(upload_url, files=files)
                
            if response.status_code == 200:
                print("[✓] نجاح: تم رفع المستند وربطه بالمعاملة بنجاح!")
                # حذف الملف المؤقت للحفاظ على النظافة الأمنية للجهاز
                os.remove(temp_path)
                return True
            else:
                print(f"[X] فشل في الرفع: {response.text}")
    except Exception as e:
        print(f"[X] حدث خطأ أثناء تشغيل ماكينة السكنر: {str(e)}")
    return False

# التقاط الرابط التفاعلي المضغط عليه من المتصفح وتفكيك أرقامه
if __name__ == "__main__":
    # الرابط القادم يكون بالشكل: cairo-scan://?letter_id=5
    if len(sys.argv) > 1:
        raw_url = sys.argv[1]
        parsed_url = urllib.parse.urlparse(raw_url)
        queries = urllib.parse.parse_qs(parsed_url.query)
        
        if 'letter_id' in queries:
            letter_id = queries['letter_id'][0]
            scan_and_upload(letter_id)
    else:
        # لتجربة البرنامج يدوياً لأغراض التطوير بدون متصفح
        scan_and_upload(1)
