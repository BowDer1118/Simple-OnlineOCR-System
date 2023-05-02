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

