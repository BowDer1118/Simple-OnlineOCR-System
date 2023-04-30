# 引入所需的模組
import asyncio
import websockets
import json
import configparser
import uuid
from datetime import datetime
from typing import Dict

# 建立一個叫做 ClientInfo 的類別
class ClientInfo:
    def __init__(self,websocket ,client_name: str, client_uuid: str, image_file_names: set):
        self.websocket=websocket
        self.client_name = client_name
        self.client_uuid = client_uuid
        self.image_file_names = image_file_names

# 在全局變量中建立一個 dictionary 叫做 clients
clients: Dict[str,ClientInfo] = {}

# 用來輸出訊息的函式
def display_message(message: str):
    # 顯示帶有時間戳的訊息
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    print(f"[{current_time}]: {message}")

# 建立 WebSocket 伺服器處理函式
async def server(websocket, path):
    try:
        # 無窮迴圈，讓伺服器持續運作
        while True:
            # 從 WebSocket 接收訊息
            message = await websocket.recv()

            # 乘載 JSON 物件
            data = None

            # 將訊息轉換為 JSON
            message_json = json.loads(message)

            # 如果收到的JSON資料只有一個key-value，代表是握手請求。
            if len(message_json) == 1:
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

            # 如果收到圖片
            elif len(message_json) == 3:
                client=clients[message_json['ClientUUID']]
                display_message(f"已收到來自客戶端名稱[{client.client_name}]的[{message_json['ImageFileName']}]圖片")
                # 組裝要傳送的 JSON 物件
                data={
                    "ResponseMessage": "SUCCESS",
                    "ImageFileName": message_json['ImageFileName'],
                    "OcrResult": "假裝完成 OCR 任務了"
                }
            # 回傳處理結果
            await websocket.send(json.dumps(data))
    except Exception as e:
        # 尋找客戶端的連線，並移除客戶端的ClientInfo
        for client_uuid, client_info in list(clients.items()): # 從所有鍵值對尋找
            if client_info.websocket == websocket:
                display_message(f"客戶端名稱[{client_info.client_name}]主動斷開連線")
                del clients[client_uuid] # 刪除元素
                break

if __name__=='__main__':
    # 讀取設定檔
    config = configparser.ConfigParser()
    config.read('settings/websocket_settings.ini')

    # 取得主機和端口
    host = config.get('WebSocket', 'host')
    port = config.get('WebSocket', 'port')

    # WebSocket伺服器
    start_server = websockets.serve(server, host, port)

    # 將協程加入事件迴圈
    asyncio.get_event_loop().run_until_complete(start_server)
    # 讓事件迴圈一直執行(這操作會阻塞主線程)
    asyncio.get_event_loop().run_forever()

