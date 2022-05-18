import asyncio, math
from typing import List
from pandas import DataFrame

from engine import  MainEngine, DataEngine
from config import TWAP_SETTING
from constant import OrderMode
from object import OrderAsking

class TWAP():
    def __init__(self, engine: MainEngine, gateway_name: str, request: OrderAsking) -> None:
        self.engine: MainEngine = engine
        self.gateway_name: str = gateway_name
        self.request: OrderAsking = request
        
        self.time: int = TWAP_SETTING.get("TIME")
        self.interval: int = TWAP_SETTING.get("INTERVAL")

        self.vt_orderids: List[str] = []
        self.traded_volume: float = 0
        self.twap_volume: float = self.get_twap_volume()

    async def run(self) -> None:
        while self.traded_volume < self.request.volume:
            self.send_order()
            await asyncio.sleep(self.interval)
            self.cancel_active_orders()
            await asyncio.sleep(1)
            self.update_traded_volume()

            self.engine.log(f"Traded {self.request.vt_symbol} {self.request.order_mode.value} {self.traded_volume}", self.gateway_name)
            self.backup()
        
            
    def send_order(self) -> List[str]:
        volume = min(self.twap_volume, self.request.volume - self.traded_volume)
        if self.request.order_mode == OrderMode.BUY:
            self.vt_orderids = self.engine.buy(self.request.vt_symbol, volume, self.gateway_name)
        elif self.request.order_mode == OrderMode.SELL:
            self.vt_orderids = self.engine.sell(self.request.vt_symbol, volume, self.gateway_name)
        elif self.request.order_mode == OrderMode.SHORT:
            self.vt_orderids = self.engine.short(self.request.vt_symbol, volume, self.gateway_name)
        elif self.request.order_mode == OrderMode.COVER:
            self.vt_orderids = self.engine.cover(self.request.vt_symbol, volume, self.gateway_name)

    def cancel_active_orders(self) -> None:
        for vt_orderid in self.vt_orderids:
            self.engine.cancel_active_order(vt_orderid)

    def update_traded_volume(self) -> None:
        for vt_orderid in self.vt_orderids:
            order = self.engine.get_order(vt_orderid)
            if order:
                self.traded_volume += order.traded

    def get_twap_volume(self) -> float:
        return max(float(math.floor(self.request.volume / (self.time / self.interval))), 1.0)

    def backup(self):
        data_engine: DataEngine = self.engine.get_engine(DataEngine.__name__)
        if data_engine is None:
            return

        data: DataFrame = data_engine.get_data(self.gateway_name)
        left_volume = self.request.volume - self.traded_volume

        idx = data.loc[
            (data["ContractID"] == self.request.ContractID) &
            (data["Op1"] == self.request.Op1) &
            (data["Op2"] == self.request.Op2)
        ].index.values[0]

        if left_volume == 0:
            data.drop(index=idx, inplace=True)
        else:  
            data.loc[idx, "Num"] = left_volume

        if data.empty:
            data_engine.delete_data(self.gateway_name)
            
        data_engine.backup_data(self.gateway_name)