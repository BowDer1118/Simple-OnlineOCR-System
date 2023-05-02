###### tags: `系統程式作業` `RabbitMQ應用`
# RabbitMQ Application - Simple Online OCR System
這是一個提供線上光學字元辨識的系統，能接受客戶端上傳圖片，然後對圖片進行光學辨識，再將辨識結果回傳給客戶端。
## 需求分析
這個光學字元辨識 (OCR) 系統需要考慮以下關鍵功能和目標：

1. **圖片上傳功能**：系統需要允許客戶端上傳要進行光學字元辨識的圖片。這可能需要處理各種圖片格式，如JPEG、PNG等，並且需要能夠處理不同大小和解析度的圖片。

2. **光學字元辨識**：一旦圖片上傳，系統需要能夠對其進行光學字元辨識。這需要使用OCR引擎（如Tesseract）來識別圖片中的文字。

3. **實時溝通**：系統需要能夠與客戶端實時溝通，以提供上傳進度、識別狀態等信息。這可能需要使用WebSocket或其他實時通訊技術來實現。
 
4. **訊息隊列**：考慮到可能有大量的識別請求，系統需要使用訊息隊列（如RabbitMQ）來管理這些請求，以確保所有請求都能夠被有效地處理。


## 系統架構、設計
![](https://i.imgur.com/wTntJIU.png)

整個系統分成4個模塊

1. **Client**: 代表要使用OCR功能的客戶端
2. **WebSocket Server**: 接收客戶端資料(圖片)的伺服器
3. **RabbitMQ Server**: 傳遞待處理的圖片和圖片的處理結果
4. **OCR Server**: 執行OCR的伺服器

系統的內部皆透過JSON格式進行通訊，各系統的通訊如下:
![](https://i.imgur.com/ATkT3T2.png)


## 使用技術、知識
1. **Multi-process Programming**: 使用Python的concurrent.futures模塊中的ProcessPoolExecutor，我們可以建立一個process pool，並將想要並行運行的任務提交給這個pool。這在需要進行大量CPU密集型運算的場景下非常有用，因為它能夠利用多核CPU的優勢。

2. **Multi-thread Programming**: 使用Python的concurrent.futures模塊中的ThreadPoolExecutor，我們可以建立一個thread pool，並將想要並行運行的任務提交給這個pool。適合密集I/O的場景。

3. **Coroutine**: 使用Python的asyncio模塊，我們可以建立和管理coroutines。coroutines是一種特殊類型的函數，它可以在執行中途暫停，並在以後的某個時間點恢復執行。這使得我們可以高效地處理I/O等待的情況，而不需要使用多threading或多processing。

4. **WebSocket Client & Server**: 使用Python的websockets和websocket-client模塊，我們可以建立WebSocket的client和server。WebSocket是一種提供全雙工通信通道的網路協定，它使得server和client可以互相發送信息。

5. **RabbitMQ**: 使用Python的pika模塊，我們可以與RabbitMQ進行交互。RabbitMQ是一種消息隊列系統，它使得我們可以在多個process或者server之間傳遞信息。

6. **Optical Character Recognition (OCR)**: 使用Tesseract OCR引擎，我們可以從圖片中識別出文字。Tesseract是一種由Google開發和維護的強大的OCR引擎，它支援多種語言並且可以在多種平台上運行。

## 系統實作、程式碼
1. **Client**


```
; WebSocket Server Address
[WebSocket]
host=127.0.0.1
port=80

;Image directory,which need to sent to WebSocket
[ImagePath]
image_dir=images

;How many thread do yo want to create for sending webSocket messages
[ThreadPool]
max_thread=4
```

```python=
import base64
import json
import copy
import os
from datetime import datetime

from concurrent.futures import ThreadPoolExecutor
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

        # 初始化來自伺服器給的client_uuid
        self.client_uuid=''

    def display_message(self, message: str):
        # 顯示帶有時間戳的訊息
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        print(f'[{current_time}][{self.client_name}] {message}')

    def on_open(self, websocket):
        #發送用戶名稱給伺服器，讓他認識我們
        self.websocket.send(json.dumps({
            "ClientName":self.client_name
        }))
        # 當與伺服器的 WebSocket 連線成功時，顯示連線訊息
        self.display_message("已與伺服器建立連線!")
        

    def on_error(self, websocket, error):
        # 當 WebSocket 連線出現錯誤時，顯示錯誤訊息
        self.display_message(f"出現錯誤，與伺服器連線中斷。原因：{error}")

    def on_message(self, websocket, message):
        # 處理從 WebSocket 伺服器接收到的訊息
        response = json.loads(message)
        if len(response) == 1:
            self.client_uuid=response['ClientUUID']
            self.display_message(f"伺服器分配給我的ClientUUID為 [{self.client_uuid}]")
            # 發送第一張圖片資訊
            self.send_image(self.image_paths[0])
        else:
            response_message = response['ResponseMessage']
            image_file_name = response['ImageFileName']
            ocr_result = response['OcrResult']

            # 根據伺服器回應的訊息進行不同的操作
            if response_message == 'PENDING':
                self.display_message(f'收到來自伺服器的回應：伺服器已經接收了[{image_file_name}]的OCR請求!')
            elif response_message == 'SUCCESS':
                self.display_message(f'收到來自伺服器的回應：圖片[{image_file_name}]的OCR結果為[{ocr_result}]')
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
            "ClientUUID":self.client_uuid,
            "ImageFileName": os.path.basename(image_path),
            "ImageBase64Data": image_data
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
    max_thread = config.getint('ThreadPool', 'max_thread')

    # 構建 WebSocket 伺服器的 url
    server_url = f"ws://{ws_host}:{ws_port}"
    # 獲取待傳送的圖片路徑列表
    image_paths = get_image_paths(image_dir)

    print(f'客戶端程式已經啟動，並使用{max_thread}個執行緒向WebSocket進行連線!')

    # 創建多執行緒池
    with ThreadPoolExecutor(max_workers=max_thread) as executor:
        tasks = []
        task_counter = 0
        # 每個任務裡的 OCRWebSocketSender 都會傳送兩張圖片到伺服器
        for i in range(0, len(image_paths), 2):
            task_counter += 1
            # 將任務提交到多執行緒池
            task = executor.submit(connect_to_server, f'客戶端 Thread {task_counter}', server_url, image_paths[i:(i+2)])
            tasks.append(task)
        # 等待所有任務執行完畢
        wait(tasks,return_when="ALL_COMPLETED")
    print(f'客戶端模擬程式已經關閉!')

```

```
客戶端程式已經啟動，並使用4個執行緒向WebSocket進行連線!
[2023-05-02 10:51:30.042834][客戶端 Thread 3] 已與伺服器建立連線!
[2023-05-02 10:51:30.043808][客戶端 Thread 3] 伺服器分配給我的ClientUUID為 [2023-05-02-10-51-30-f6ca2b83-b397-42cf-8c54-62b39948a586]
[2023-05-02 10:51:30.044805][客戶端 Thread 3] 已向伺服器發送 images/Screenshot_4.png 圖片!
[2023-05-02 10:51:30.045802][客戶端 Thread 4] 已與伺服器建立連線!
[2023-05-02 10:51:30.045802][客戶端 Thread 3] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_4.png]的OCR請求!
[2023-05-02 10:51:30.045802][客戶端 Thread 1] 已與伺服器建立連線!
[2023-05-02 10:51:30.046800][客戶端 Thread 4] 伺服器分配給我的ClientUUID為 [2023-05-02-10-51-30-fbda4886-b991-427e-9115-ff709243e1e6]
[2023-05-02 10:51:30.046800][客戶端 Thread 1] 伺服器分配給我的ClientUUID為 [2023-05-02-10-51-30-829519f9-2923-4a06-bf34-5baad3026b21]
[2023-05-02 10:51:30.046800][客戶端 Thread 2] 已與伺服器建立連線!
[2023-05-02 10:51:30.046800][客戶端 Thread 2] 伺服器分配給我的ClientUUID為 [2023-05-02-10-51-30-3a0c84f8-3126-48c6-9983-82b32e0ac963]
[2023-05-02 10:51:30.046800][客戶端 Thread 1] 已向伺服器發送 images/Screenshot_1.png 圖片!
[2023-05-02 10:51:30.047796][客戶端 Thread 4] 已向伺服器發送 images/Screenshot_6.png 圖片!
[2023-05-02 10:51:30.047796][客戶端 Thread 2] 已向伺服器發送 images/Screenshot_2.png 圖片!
[2023-05-02 10:51:30.048793][客戶端 Thread 1] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_1.png]的OCR請求!
[2023-05-02 10:51:30.049790][客戶端 Thread 4] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_6.png]的OCR請求!
[2023-05-02 10:51:30.049790][客戶端 Thread 2] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_2.png]的OCR請求!
[2023-05-02 10:51:30.146532][客戶端 Thread 2] 收到來自伺服器的回應：圖片[Screenshot_2.png]的OCR結果為[]
[2023-05-02 10:51:30.147533][客戶端 Thread 2] 已向伺服器發送 images/Screenshot_3.png 圖片!
[2023-05-02 10:51:30.150521][客戶端 Thread 1] 收到來自伺服器的回應：圖片[Screenshot_1.png]的OCR結果為[This

]
[2023-05-02 10:51:30.151519][客戶端 Thread 2] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_3.png]的OCR請求!
[2023-05-02 10:51:30.151519][客戶端 Thread 1] 已向伺服器發送 images/Screenshot_10.png 圖片!
[2023-05-02 10:51:30.152517][客戶端 Thread 3] 收到來自伺服器的回應：圖片[Screenshot_4.png]的OCR結果為[English

]
[2023-05-02 10:51:30.153514][客戶端 Thread 3] 已向伺服器發送 images/Screenshot_5.png 圖片!
[2023-05-02 10:51:30.154513][客戶端 Thread 1] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_10.png]的OCR請求!
[2023-05-02 10:51:30.155508][客戶端 Thread 3] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_5.png]的OCR請求!
[2023-05-02 10:51:30.156507][客戶端 Thread 4] 收到來自伺服器的回應：圖片[Screenshot_6.png]的OCR結果為[For‘

]
[2023-05-02 10:51:30.158501][客戶端 Thread 4] 已向伺服器發送 images/Screenshot_7.png 圖片!
[2023-05-02 10:51:30.159498][客戶端 Thread 4] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_7.png]的OCR請求!
[2023-05-02 10:51:30.241278][客戶端 Thread 2] 收到來自伺服器的回應：圖片[Screenshot_3.png]的OCR結果為[]
[2023-05-02 10:51:30.242278][客戶端 Thread 2] 所有圖片已經傳送完畢，主動斷開與伺服器的連線！
[2023-05-02 10:51:30.242278][客戶端 Thread 4] 收到來自伺服器的回應：圖片[Screenshot_7.png]的OCR結果為[the

]
[2023-05-02 10:51:30.245268][客戶端 Thread 4] 所有圖片已經傳送完畢，主動斷開與伺服器的連線！
[2023-05-02 10:51:30.245268][客戶端 Thread 5] 已與伺服器建立連線!
[2023-05-02 10:51:30.246265][客戶端 Thread 5] 伺服器分配給我的ClientUUID為 [2023-05-02-10-51-30-df42c8ad-2f01-4f93-b4fd-926c598dae37]
[2023-05-02 10:51:30.246265][客戶端 Thread 5] 已向伺服器發送 images/Screenshot_8.png 圖片!
[2023-05-02 10:51:30.249258][客戶端 Thread 1] 收到來自伺服器的回應：圖片[Screenshot_10.png]的OCR結果為[Execute.

]
[2023-05-02 10:51:30.250254][客戶端 Thread 5] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_8.png]的OCR請求!
[2023-05-02 10:51:30.250254][客戶端 Thread 1] 所有圖片已經傳送完畢，主動斷開與伺服器的連線！
[2023-05-02 10:51:30.251253][客戶端 Thread 3] 收到來自伺服器的回應：圖片[Screenshot_5.png]的OCR結果為[sentance.

]
[2023-05-02 10:51:30.252249][客戶端 Thread 3] 所有圖片已經傳送完畢，主動斷開與伺服器的連線！
[2023-05-02 10:51:30.309098][客戶端 Thread 5] 收到來自伺服器的回應：圖片[Screenshot_8.png]的OCR結果為[OCR

]
[2023-05-02 10:51:30.311093][客戶端 Thread 5] 已向伺服器發送 images/Screenshot_9.png 圖片!
[2023-05-02 10:51:30.313086][客戶端 Thread 5] 收到來自伺服器的回應：伺服器已經接收了[Screenshot_9.png]的OCR請求!
[2023-05-02 10:51:30.376917][客戶端 Thread 5] 收到來自伺服器的回應：圖片[Screenshot_9.png]的OCR結果為[Server

]
[2023-05-02 10:51:30.377916][客戶端 Thread 5] 所有圖片已經傳送完畢，主動斷開與伺服器的連線！
客戶端模擬程式已經關閉!
```

2. **WebSocket Server**
```
[WebSocket]
host=127.0.0.1
port=80

[RabbitMQ]
host=127.0.0.1
port=5672
account=guest
password=guest
```

```python=
# 引入所需的模組
import asyncio
import websockets
import json
import configparser
import uuid
from datetime import datetime
from typing import Dict
import aio_pika


# 建立一個叫做 ClientInfo 的類別
class ClientInfo:
    def __init__(self,websocket ,client_name: str, client_uuid: str, image_file_names: set):
        self.websocket=websocket
        self.client_name = client_name
        self.client_uuid = client_uuid
        self.image_file_names = image_file_names

# 在全局變量中建立一個 dictionary 叫做 clients
clients: Dict[str,ClientInfo] = {}

#  rabbitMQ的連結
channel = None

# 用來輸出訊息的函式
def display_message(message: str):
    # 顯示帶有時間戳的訊息
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    print(f"[{current_time}][WebSocket伺服器] {message}")

async def handle_handshake(websocket,message_json):
    # 生成一個帶有時間資訊的 uuid 字串
    current_time = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    client_uuid = f"{current_time}-{uuid.uuid4()}"

    # 創建一個 ClientInfo 物件
    client_info = ClientInfo(websocket,message_json['ClientName'], client_uuid, set())

    # 將 uuid 和 ClientInfo 物件加入到 clients 字典中
    clients[client_uuid] = client_info

    # 組裝要傳送的 JSON 物件
    data={"ClientUUID": client_uuid}

    # 顯示已接受客戶端的連線請求
    display_message(f"已接受客戶端名稱[{client_info.client_name}]的連線請求，並分配給客戶端UUID[{client_uuid}]")

    return data

async def send_to_rabbitmq(message_json):
    #擴充JSON內容
    message_json['OcrResult']=''
    await channel.default_exchange.publish(
        #由於rabbitMQ中的queue存放的是byte資料，因此要使用encode()將JSON編碼成bytes
        aio_pika.Message(body=json.dumps(message_json).encode()),
        routing_key='pending_queue',
    )
    

async def handle_image_upload(message_json):
    client=clients[message_json['ClientUUID']]
    
    #將圖片名稱加入image_file_names中
    image_file_name=message_json['ImageFileName']
    client.image_file_names.add(image_file_name)

    display_message(f"已收到來自客戶端名稱[{client.client_name}]的[{image_file_name}]圖片")

    #真正的handle_image_upload任務:發送一個JSON到RabbitMQ中的pending queue中
    await send_to_rabbitmq(message_json)
    display_message(f"已將圖片資訊[{image_file_name}]傳到 RabbitMQ 伺服器!")

    #產生handle_image_upload處理完畢後，要返回給客戶端的資料
    data={
        "ResponseMessage": "PENDING",
        "ImageFileName": image_file_name,
        "OcrResult": "尚未得到OCR結果"
    }

    return data


async def handle_websocket_error(websocket,error_message):
    # 尋找客戶端的連線，並移除客戶端的ClientInfo
    for client_uuid, client_info in list(clients.items()): # 從所有鍵值對尋找
        if client_info.websocket == websocket:
            display_message(f"伺服器與客戶端名稱[{client_info.client_name}]斷開連線，原因:{error_message}")
            del clients[client_uuid] # 刪除元素
            break

# 建立 WebSocket 伺服器處理函式
async def server(websocket, path):
    try:
        # 無窮迴圈，讓伺服器持續運作
        while True:
            try:
                # 從 WebSocket 接收訊息，最長等待30秒，超時會引發異常
                message = await asyncio.wait_for(websocket.recv(), timeout=30)
                # 將訊息轉換為 JSON
                message_json = json.loads(message)
                
                # 一個字典，用來裝伺服器要回應給客戶端的JSON
                data = None
                
                # 如果收到的JSON資料只有一個key-value，代表是握手請求。
                if len(message_json) == 1:
                    data = await handle_handshake(websocket,message_json)
                # 如果收到的JSON資料有3個key-value，代表收到上傳的圖片
                elif len(message_json) == 3:
                    data = await handle_image_upload(message_json)
                # 回傳處理結果
                await websocket.send(json.dumps(data))
            except asyncio.TimeoutError:
                # 如果等待30秒仍未接收到訊息，中斷連線並處理錯誤
                await handle_websocket_error(websocket,"已等待客戶端30秒，但仍未收到客戶端的訊息。")
                await websocket.close()
                break
    except Exception as e: #處理意外狀況
        await handle_websocket_error(websocket,"通訊發生意外狀況，客戶端可能已經主動關閉連線。")

# 定義處理消息的協程
async def handle_result_queue_message(message: aio_pika.IncomingMessage):
    async with message.process():  # 確保消息在處理完後會被確認
        # 將消息轉換為 JSON
        message_json = json.loads(message.body.decode())

        # 從 JSON 中獲取資訊
        client_uuid = message_json['ClientUUID']
        image_file_name = message_json['ImageFileName']
        ocr_result = message_json['OcrResult']

        # 從 clients 中獲取對應的 ClientInfo 物件
        client_info = clients.get(client_uuid, None)

        # 如果找到對應的 ClientInfo 物件
        if client_info is not None:
            # 組裝要傳送的 JSON 物件
            data = {
                "ResponseMessage": "SUCCESS",
                "ImageFileName": image_file_name,
                "OcrResult": ocr_result
            }

            # 透過 websocket 傳送 JSON 資料
            await client_info.websocket.send(json.dumps(data))

            # 從 image_file_names 中刪除圖片名稱
            client_info.image_file_names.discard(image_file_name)

            # 顯示處理結果
            display_message(f"已經將圖片[{image_file_name}]的處理結果傳送給客戶端[{client_info.client_name}]。")


# 建立一個協程來監聽 result_queue
async def monitor_result_queue():
    # 獲取 result_queue
    result_queue = await channel.declare_queue('result_queue')
    # 將處理消息的協程註冊到 result_queue 中，開始監聽消息
    await result_queue.consume(handle_result_queue_message)


if __name__=='__main__':
    # 讀取設定檔
    config = configparser.ConfigParser()
    config.read('settings/websocket_server_settings.ini')

    # 取得WebSocket主機和端口
    host = config.get('WebSocket', 'host')
    port = config.get('WebSocket', 'port')

    # RabbitMQ 伺服器的設定
    rabbitmq_host = config.get('RabbitMQ', 'host')
    rabbitmq_port =config.get('RabbitMQ','port')
    rabbitmq_user = config.get('RabbitMQ', 'account')
    rabbitmq_password = config.get('RabbitMQ', 'password')
    
    display_message('WebSocket伺服器已啟動!')

    loop=asyncio.get_event_loop()

    # 建立到 RabbitMQ 的連接
    rabbitmq_connection = loop.run_until_complete(
        aio_pika.connect_robust(
            f"amqp://{rabbitmq_user}:{rabbitmq_password}@{rabbitmq_host}:{rabbitmq_port}/"
        )
    )

    channel = loop.run_until_complete(rabbitmq_connection.channel())

    # 宣告 pending_queue
    loop.run_until_complete(channel.declare_queue('pending_queue', durable=False))
    
    # 將監聽 result_queue 的協程加入事件迴圈
    loop.create_task(monitor_result_queue())


    # WebSocket伺服器
    start_server = websockets.serve(server, host, port)

    # 將協程加入事件迴圈
    loop.run_until_complete(start_server)
    # 讓事件迴圈一直執行(這操作會阻塞主線程)
    loop.run_forever()
    
```

```
[2023-05-02 10:51:27.923378][WebSocket伺服器] WebSocket伺服器已啟動!
[2023-05-02 10:51:30.043808][WebSocket伺服器] 已接受客戶端名稱[客戶端 Thread 3]的連線請求，並分配給客戶端UUID[2023-05-02-10-51-30-f6ca2b83-b397-42cf-8c54-62b39948a586]
[2023-05-02 10:51:30.044805][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 3]的[Screenshot_4.png]圖片
[2023-05-02 10:51:30.045802][WebSocket伺服器] 已將圖片資訊[Screenshot_4.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.045802][WebSocket伺服器] 已接受客戶端名稱[客戶端 Thread 4]的連線請求，並分配給客戶端UUID[2023-05-02-10-51-30-fbda4886-b991-427e-9115-ff709243e1e6]
[2023-05-02 10:51:30.046800][WebSocket伺服器] 已接受客戶端名稱[客戶端 Thread 1]的連線請求，並分配給客戶端UUID[2023-05-02-10-51-30-829519f9-2923-4a06-bf34-5baad3026b21]
[2023-05-02 10:51:30.046800][WebSocket伺服器] 已接受客戶端名稱[客戶端 Thread 2]的連線請求，並分配給客戶端UUID[2023-05-02-10-51-30-3a0c84f8-3126-48c6-9983-82b32e0ac963]
[2023-05-02 10:51:30.047796][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 1]的[Screenshot_1.png]圖片
[2023-05-02 10:51:30.047796][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 4]的[Screenshot_6.png]圖片
[2023-05-02 10:51:30.047796][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 2]的[Screenshot_2.png]圖片
[2023-05-02 10:51:30.048793][WebSocket伺服器] 已將圖片資訊[Screenshot_1.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.048793][WebSocket伺服器] 已將圖片資訊[Screenshot_6.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.048793][WebSocket伺服器] 已將圖片資訊[Screenshot_2.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.146532][WebSocket伺服器] 已經將圖片[Screenshot_2.png]的處理結果傳送給客戶端[客戶端 Thread 2]。
[2023-05-02 10:51:30.147533][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 2]的[Screenshot_3.png]圖片
[2023-05-02 10:51:30.150521][WebSocket伺服器] 已經將圖片[Screenshot_1.png]的處理結果傳送給客戶端[客戶端 Thread 1]。
[2023-05-02 10:51:30.150521][WebSocket伺服器] 已將圖片資訊[Screenshot_3.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.151519][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 1]的[Screenshot_10.png]圖片
[2023-05-02 10:51:30.152517][WebSocket伺服器] 已經將圖片[Screenshot_4.png]的處理結果傳送給客戶端[客戶端 Thread 3]。
[2023-05-02 10:51:30.154513][WebSocket伺服器] 已將圖片資訊[Screenshot_10.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.154513][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 3]的[Screenshot_5.png]圖片
[2023-05-02 10:51:30.155508][WebSocket伺服器] 已將圖片資訊[Screenshot_5.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.156507][WebSocket伺服器] 已經將圖片[Screenshot_6.png]的處理結果傳送給客戶端[客戶端 Thread 4]。
[2023-05-02 10:51:30.158501][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 4]的[Screenshot_7.png]圖片
[2023-05-02 10:51:30.159498][WebSocket伺服器] 已將圖片資訊[Screenshot_7.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.241278][WebSocket伺服器] 已經將圖片[Screenshot_3.png]的處理結果傳送給客戶端[客戶端 Thread 2]。
[2023-05-02 10:51:30.242278][WebSocket伺服器] 已經將圖片[Screenshot_7.png]的處理結果傳送給客戶端[客戶端 Thread 4]。
[2023-05-02 10:51:30.244270][WebSocket伺服器] 伺服器與客戶端名稱[客戶端 Thread 2]斷開連線，原因:通訊發生意外狀況，客戶端可能已經主動關閉連線。
[2023-05-02 10:51:30.246265][WebSocket伺服器] 已接受客戶端名稱[客戶端 Thread 5]的連線請求，並分配給客戶端UUID[2023-05-02-10-51-30-df42c8ad-2f01-4f93-b4fd-926c598dae37]
[2023-05-02 10:51:30.246265][WebSocket伺服器] 伺服器與客戶端名稱[客戶端 Thread 4]斷開連線，原因:通訊發生意外狀況，客戶端可能已經主動關閉連線。
[2023-05-02 10:51:30.247265][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 5]的[Screenshot_8.png]圖片
[2023-05-02 10:51:30.249258][WebSocket伺服器] 已經將圖片[Screenshot_10.png]的處理結果傳送給客戶端[客戶端 Thread 1]。
[2023-05-02 10:51:30.249258][WebSocket伺服器] 已將圖片資訊[Screenshot_8.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.251253][WebSocket伺服器] 已經將圖片[Screenshot_5.png]的處理結果傳送給客戶端[客戶端 Thread 3]。
[2023-05-02 10:51:30.252249][WebSocket伺服器] 伺服器與客戶端名稱[客戶端 Thread 1]斷開連線，原因:通訊發生意外狀況，客戶端可能已經主動關閉連線。
[2023-05-02 10:51:30.253246][WebSocket伺服器] 伺服器與客戶端名稱[客戶端 Thread 3]斷開連線，原因:通訊發生意外狀況，客戶端可能已經主動關閉連線。
[2023-05-02 10:51:30.309098][WebSocket伺服器] 已經將圖片[Screenshot_8.png]的處理結果傳送給客戶端[客戶端 Thread 5]。
[2023-05-02 10:51:30.312090][WebSocket伺服器] 已收到來自客戶端名稱[客戶端 Thread 5]的[Screenshot_9.png]圖片
[2023-05-02 10:51:30.312090][WebSocket伺服器] 已將圖片資訊[Screenshot_9.png]傳到 RabbitMQ 伺服器!
[2023-05-02 10:51:30.375919][WebSocket伺服器] 已經將圖片[Screenshot_9.png]的處理結果傳送給客戶端[客戶端 Thread 5]。
[2023-05-02 10:51:30.378910][WebSocket伺服器] 伺服器與客戶端名稱[客戶端 Thread 5]斷開連線，原因:通訊發生意外狀況，客戶端可能已經主動關閉連線。
```

3. **OCR Server**
```
[tesseract_location]
path=C:\Program Files (x86)\Tesseract-OCR\tesseract.exe

[RabbitMQ]
host=127.0.0.1
port=5672
account=guest
password=guest

[ProcessPool]
max_process=4
```
```python=
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

```

```
OCR伺服器已啟動!
[2023-05-02 10:51:25.593330][OCR_Server][Process 2] 已啟動，並開始監聽RabbitMQ伺服器!
[2023-05-02 10:51:25.593330][OCR_Server][Process 1] 已啟動，並開始監聽RabbitMQ伺服器!
[2023-05-02 10:51:25.598317][OCR_Server][Process 3] 已啟動，並開始監聽RabbitMQ伺服器!
[2023-05-02 10:51:25.600311][OCR_Server][Process 4] 已啟動，並開始監聽RabbitMQ伺服器!
[2023-05-02 10:51:30.045802][OCR_Server][Process 2] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-f6ca2b83-b397-42cf-8c54-62b39948a586]的[Screenshot_4.png]資料!
[2023-05-02 10:51:30.047796][OCR_Server][Process 1] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-829519f9-2923-4a06-bf34-5baad3026b21]的[Screenshot_1.png]資料!
[2023-05-02 10:51:30.048793][OCR_Server][Process 3] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-fbda4886-b991-427e-9115-ff709243e1e6]的[Screenshot_6.png]資料!
[2023-05-02 10:51:30.048793][OCR_Server][Process 4] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-3a0c84f8-3126-48c6-9983-82b32e0ac963]的[Screenshot_2.png]資料!
[2023-05-02 10:51:30.144537][OCR_Server][Process 4] 已將ClientUUID[2023-05-02-10-51-30-3a0c84f8-3126-48c6-9983-82b32e0ac963]的[Screenshot_2.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.148528][OCR_Server][Process 1] 已將ClientUUID[2023-05-02-10-51-30-829519f9-2923-4a06-bf34-5baad3026b21]的[Screenshot_1.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.150521][OCR_Server][Process 2] 已將ClientUUID[2023-05-02-10-51-30-f6ca2b83-b397-42cf-8c54-62b39948a586]的[Screenshot_4.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.150521][OCR_Server][Process 2] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-3a0c84f8-3126-48c6-9983-82b32e0ac963]的[Screenshot_3.png]資料!
[2023-05-02 10:51:30.154513][OCR_Server][Process 1] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-829519f9-2923-4a06-bf34-5baad3026b21]的[Screenshot_10.png]資料!
[2023-05-02 10:51:30.155508][OCR_Server][Process 3] 已將ClientUUID[2023-05-02-10-51-30-fbda4886-b991-427e-9115-ff709243e1e6]的[Screenshot_6.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.156507][OCR_Server][Process 3] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-f6ca2b83-b397-42cf-8c54-62b39948a586]的[Screenshot_5.png]資料!
[2023-05-02 10:51:30.159498][OCR_Server][Process 4] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-fbda4886-b991-427e-9115-ff709243e1e6]的[Screenshot_7.png]資料!
[2023-05-02 10:51:30.238287][OCR_Server][Process 2] 已將ClientUUID[2023-05-02-10-51-30-3a0c84f8-3126-48c6-9983-82b32e0ac963]的[Screenshot_3.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.241278][OCR_Server][Process 4] 已將ClientUUID[2023-05-02-10-51-30-fbda4886-b991-427e-9115-ff709243e1e6]的[Screenshot_7.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.247265][OCR_Server][Process 1] 已將ClientUUID[2023-05-02-10-51-30-829519f9-2923-4a06-bf34-5baad3026b21]的[Screenshot_10.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.248261][OCR_Server][Process 2] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-df42c8ad-2f01-4f93-b4fd-926c598dae37]的[Screenshot_8.png]資料!
[2023-05-02 10:51:30.250254][OCR_Server][Process 3] 已將ClientUUID[2023-05-02-10-51-30-f6ca2b83-b397-42cf-8c54-62b39948a586]的[Screenshot_5.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.308099][OCR_Server][Process 2] 已將ClientUUID[2023-05-02-10-51-30-df42c8ad-2f01-4f93-b4fd-926c598dae37]的[Screenshot_8.png]辨識結果放到RabbitMQ伺服器!
[2023-05-02 10:51:30.312090][OCR_Server][Process 1] 已從RabbitMQ伺服器獲取ClientUUID[2023-05-02-10-51-30-df42c8ad-2f01-4f93-b4fd-926c598dae37]的[Screenshot_9.png]資料!
[2023-05-02 10:51:30.374921][OCR_Server][Process 1] 已將ClientUUID[2023-05-02-10-51-30-df42c8ad-2f01-4f93-b4fd-926c598dae37]的[Screenshot_9.png]辨識結果放到RabbitMQ伺服器!
```

## 資料參考
1. RabbitMQ安裝: https://juejin.cn/post/7101855270854197284
2. Coroutine使用方法: https://www.maxlist.xyz/2020/03/29/python-coroutine/amp/
3. OCR引擎: https://github.com/tesseract-ocr/tesseract
4. WebSocket協定: https://hackmd.io/@Heidi-Liu/javascript-websocket
5. ChatGPT(GPT-4 Model): https://chat.openai.com/

