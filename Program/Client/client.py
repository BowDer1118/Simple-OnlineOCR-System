import base64
import json
import copy
import os
from datetime import datetime

from concurrent.futures import ProcessPoolExecutor
from concurrent.futures import wait
import configparser
from websocket import WebSocketApp

class OCRWebSocketSender:
    def __init__(self, client_name:str, server_url:str, image_paths:list[str]):
        # 初始化 WebSocketApp 物件並設定各種事件的回調函數
        self.websocket = WebSocketApp(server_url,
                               on_open=self.on_open,
                               on_error=self.on_error,
                               on_message=self.on_message,
                               on_close=self.on_close)

        # 初始化客戶端名稱
        self.client_name = client_name

        # 初始化待傳遞的圖片路徑列表
        self.image_paths = copy.deepcopy(image_paths)
        
        # 初始化伺服器回應計數器
        self.response_counter = 0

    def display_message(self, message: str):
        # 顯示帶有時間戳的訊息
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        print(f'[{current_time}][{self.client_name}] {message}')

    def on_open(self, websocket):
        # 當與伺服器的 WebSocket 連線成功時，顯示連線訊息
        self.display_message("已與伺服器建立連線!")
        
        # 發送第一張圖片資訊
        self.send_image(self.image_paths[0])

    def on_error(self, websocket, error):
        # 當 WebSocket 連線出現錯誤時，顯示錯誤訊息
        self.display_message(f"出現錯誤，與伺服器連線中斷。原因：{error}")

    def on_message(self, websocket, message):
        # 處理從 WebSocket 伺服器接收到的訊息
        response = json.loads(message)
        response_message = response['ResponseMessage']
        image_file_name = response['ImageFileName']
        ocr_result = response['OcrResult']

        # 根據伺服器回應的訊息進行不同的操作
        if response_message == 'PENDING':
            self.display_message(f'收到來自伺服器的回應： 伺服器已經接收了 {image_file_name}的OCR請求!')
        elif response_message == 'SUCCESS':
            self.display_message(f'收到來自伺服器的回應： 圖片{image_file_name}的OCR結果為 {ocr_result}')
            # 如果還有未傳送的圖片，則繼續傳送下一張
            self.response_counter += 1
            if self.response_counter < len(self.image_paths):
                self.send_image(self.image_paths[self.response_counter])
            else:
                # 如果所有圖片都已傳送完畢，則主動關閉連線
                self.display_message(f'所有圖片已經傳送完畢，主動斷開與伺服器的連線！')
                self.websocket.close()

    def on_close(self, websocket, *args, **kwargs):
        # 當與伺服器的 WebSocket 連線斷開時，顯示連線結束的訊息
        self.display_message("已與伺服器斷開連線!")
        

    def send_image(self, image_path:str):
        # 將圖片以 base64 格式進行編碼並傳送至伺服器
        with open(image_path, "rb") as image_file:
            image_data = base64.b64encode(image_file.read()).decode('utf-8')

        # 組裝要傳送的 JSON 資料
        data = {
            "ClientName":self.client_name,
            "ImageFileName": os.path.basename(image_path),
            "ImageData": image_data
        }

        # 發送圖片資料
        self.websocket.send(json.dumps(data))
        self.display_message(f"已向伺服器發送 {image_path} 圖片!")

    def start(self):
        # 啟動 WebSocket 連線
        self.websocket.run_forever()


# 輔助函數：獲取指定資料夾下所有圖片的路徑
def get_image_paths(image_dir:str) -> list[str]:
    # 獲取指定資料夾下的所有檔案名稱
    files = os.listdir(image_dir)

    image_paths = []
    # 遍歷資料夾下的所有檔案
    for f in files:
        # 如果檔案是圖片（以 .png、.jpg 或 .jpeg 結尾），則將其路徑加入到 image_paths 列表中
        if f.endswith(('.png', '.jpg', '.jpeg')):
            image_paths.append(image_dir + '/' + f)
        else:
            print(f'在{image_dir}資料夾下，找到非圖片的檔案: {f}')
    return image_paths

def connect_to_server(client_name:str, server_url:str, image_paths:list[str]):
    # 創建一個 OCRWebSocketSender 物件並開始與 WebSocket 伺服器連線
    ocr_request = OCRWebSocketSender(client_name, server_url, image_paths)
    ocr_request.start()

if __name__ == "__main__":
    # 解析配置文件中的設定
    config = configparser.ConfigParser()
    config.read('settings/client_settings.ini')
    ws_host = config.get('WebSocket', 'host')
    ws_port = config.getint('WebSocket', 'port')
    image_dir = config.get('ImagePath', 'image_dir')
    worker_count = config.getint('ProcessPool', 'worker')

    # 構建 WebSocket 伺服器的 url
    server_url = f"ws://{ws_host}:{ws_port}"
    # 獲取待傳送的圖片路徑列表
    image_paths = get_image_paths(image_dir)

    print(f'客戶端模擬程式已經啟動!')

    # 創建多進程池
    with ProcessPoolExecutor(max_workers=worker_count) as executor:
        tasks = []
        task_counter = 0
        # 每個任務裡的 OCRWebSocketSender 都會傳送兩張圖片到伺服器
        for i in range(0, len(image_paths), 2):
            task_counter += 1
            # 將任務提交到多進程池
            task = executor.submit(connect_to_server, f'客戶端 Process{task_counter}', server_url, image_paths[i:(i+2)])
            tasks.append(task)
        # 等待所有任務執行完畢
        wait(tasks)
    print(f'客戶端模擬程式已經關閉!')



