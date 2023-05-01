import pika
import json
import base64
from PIL import Image
from io import BytesIO
import pytesseract
from datetime import datetime
import configparser

# 用來輸出訊息的函式
def display_message(message: str):
    # 顯示帶有時間戳的訊息
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    print(f"[{current_time}][OCR Server]: {message}")

# 定義圖片識別函數
def image_to_text(image_base64, tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path  # 從設定檔讀取Tesseract路徑
    image_data = base64.b64decode(image_base64)
    image = Image.open(BytesIO(image_data))
    text = pytesseract.image_to_string(image, lang='eng')
    return text

def callback(ch, method, properties, body):
        data = json.loads(body)
        client_uuid=data['ClientUUID']
        image_file_name=data['ImageFileName']
        display_message(f'已從RabbitMQ伺服器獲取ClientUUID[{client_uuid}]的[{image_file_name}]資料!')
        
        #將圖片資料進行OCR並寫入OCR結果
        data['OcrResult'] = image_to_text(data['ImageBase64Data'], tesseract_path)

        del data['ImageBase64Data']

        channel.basic_publish(exchange='',
                            routing_key='result_queue',
                            body=json.dumps(data))
        
        display_message(f'已將ClientUUID[{client_uuid}]的[{image_file_name}]辨識結果放到RabbitMQ伺服器!')

if __name__=='__main__':
    # 讀取設定檔
    config = configparser.ConfigParser()
    config.read('settings/ocr_server_settings.ini')

    # Tesseract OCR引擎的位置
    tesseract_path = config.get('tesseract_location', 'path')

    # RabbitMQ 伺服器的設定
    rabbitmq_host = config.get('RabbitMQ', 'host')
    rabbitmq_port = config.getint('RabbitMQ', 'port')  # 讀取整數型態的端口號
    rabbitmq_user = config.get('RabbitMQ', 'account')
    rabbitmq_password = config.get('RabbitMQ', 'password')

    # 連接到 RabbitMQ，使用設定檔的參數
    credentials = pika.PlainCredentials(rabbitmq_user, rabbitmq_password)
    connection = pika.BlockingConnection(pika.ConnectionParameters(rabbitmq_host, rabbitmq_port, '/', credentials))
    channel = connection.channel()

    channel.queue_declare(queue='pending_queue')
    channel.queue_declare(queue='result_queue')

    # 設定待處理隊列的回呼函數
    channel.basic_consume(queue='pending_queue', on_message_callback=callback, auto_ack=True)

    channel.start_consuming()
