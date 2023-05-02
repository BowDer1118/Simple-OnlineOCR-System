# 導入需要的模組
import pika
import json
import base64
from PIL import Image
from io import BytesIO
import pytesseract
from datetime import datetime
import configparser
from concurrent.futures import ProcessPoolExecutor, wait

# 定義RabbitMQ消費者類
class RabbitMQConsumer:
    def __init__(self, process_name: str):
        self.process_name = process_name
        # 使用 configparser 讀取設定檔
        self.config = configparser.ConfigParser()
        self.config.read('settings/ocr_server_settings.ini')
        # 從設定檔中讀取 tesseract 路徑
        self.tesseract_path = self.config.get('tesseract_location', 'path')
        # 從設定檔中讀取 RabbitMQ 的連接資訊
        self.rabbitmq_host = self.config.get('RabbitMQ', 'host')
        self.rabbitmq_port = self.config.getint('RabbitMQ', 'port') 
        self.rabbitmq_user = self.config.get('RabbitMQ', 'account')
        self.rabbitmq_password = self.config.get('RabbitMQ', 'password')

    # 顯示訊息的方法
    def display_message(self, message: str):
        # 獲取當前時間並格式化
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        print(f"[{current_time}][OCR_Server][{self.process_name}] {message}")

    # 將圖片轉換為文字的方法
    def image_to_text(self, image_base64):
        # 解碼 base64 圖片數據
        image_data = base64.b64decode(image_base64)
        # 將二進制數據轉換為 PIL Image
        image = Image.open(BytesIO(image_data))
        # 使用 pytesseract 將圖片轉換為文字
        text = pytesseract.image_to_string(image, lang='eng')
        return text

    # 處理 RabbitMQ 消息的回調方法
    def callback(self, ch, method, properties, body):
        # 將消息體解析為 JSON
        data = json.loads(body)
        client_uuid = data['ClientUUID']
        image_file_name = data['ImageFileName']
        self.display_message(f'已從RabbitMQ伺服器獲取ClientUUID[{client_uuid}]的[{image_file_name}]資料!')
        # 將圖片數據轉換為文字
        data['OcrResult'] = self.image_to_text(data['ImageBase64Data'])
        # 刪除圖片數據以節省空間
        del data['ImageBase64Data']
        # 發送處理結果至 RabbitMQ
        ch.basic_publish(exchange='',
                         routing_key='result_queue',
                         body=json.dumps(data))
        self.display_message(f'已將ClientUUID[{client_uuid}]的[{image_file_name}]辨識結果放到RabbitMQ伺服器!')

    # 監控等待處理的隊列
    def monitor_pending_queue(self):
        # 設定 tesseract 的路徑
        pytesseract.pytesseract.tesseract_cmd = self.tesseract_path  
        # 建立 RabbitMQ 連接
        credentials = pika.PlainCredentials(self.rabbitmq_user, self.rabbitmq_password)
        connection = pika.BlockingConnection(pika.ConnectionParameters(self.rabbitmq_host, self.rabbitmq_port, '/', credentials))
        self.display_message(f'已啟動，並開始監聽RabbitMQ伺服器!')

        # 創建 RabbitMQ 頻道
        channel = connection.channel()

        # 宣告隊列
        channel.queue_declare(queue='pending_queue')
        channel.queue_declare(queue='result_queue')

        # 設定消費者回調方法並啟動消費
        channel.basic_consume(queue='pending_queue', on_message_callback=self.callback, auto_ack=True)
        
        channel.start_consuming()

# 創建單一消費者並監控隊列
def process_task(process_name):
    consumer = RabbitMQConsumer(process_name)
    consumer.monitor_pending_queue()

# 主函數
if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read('settings/ocr_server_settings.ini')
    # 從設定檔讀取最大進程數
    max_process = config.getint('Process', 'max_process')

    # 創建多進程的執行池
    process_pool = ProcessPoolExecutor(max_workers=max_process)
    tasks = []

    # 對每個進程，都提交一個任務到執行池
    for i in range(max_process):
        process_pool.submit(process_task, f'Process {i+1}')

    print(f'OCR伺服器已啟動!')

    # 等待所有的進程完成
    wait(tasks, return_when="ALL_COMPLETED")
