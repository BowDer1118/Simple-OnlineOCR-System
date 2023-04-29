# 引入所需的模組
import asyncio
import websockets
import json
import configparser



# 建立WebSocket伺服器處理函式
async def server(websocket, path):
    try:
        # 無窮迴圈，讓伺服器持續運作
        while True:
            # 從WebSocket接收訊息
            message = await websocket.recv()

            # 將訊息轉換為JSON
            message_json = json.loads(message)
            
            # 組裝要傳送的 JSON 物件
            data = {
                "ResponseMessage":"SUCCESS",
                "ImageFileName": message_json['ImageFileName'],
                "OcrResult": "假裝完成OCR任務了"
            }

            # 回傳處理結果
            await websocket.send(json.dumps(data))
    except Exception as e:
        print(f"客戶端主動關閉連線!")

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
    #讓事件迴圈一直執行(這操作會阻塞主線程)
    asyncio.get_event_loop().run_forever()
