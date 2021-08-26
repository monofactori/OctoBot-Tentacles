#  Drakkar-Software OctoBot-Tentacles
#  Copyright (c) Drakkar-Software, All rights reserved.
#
#  This library is free software; you can redistribute it and/or
#  modify it under the terms of the GNU Lesser General Public
#  License as published by the Free Software Foundation; either
#  version 3.0 of the License, or (at your option) any later version.
#
#  This library is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
#  Lesser General Public License for more details.
#
#  You should have received a copy of the GNU Lesser General Public
#  License along with this library.
import copy
import math

import ccxt

import octobot_trading.errors
import octobot_trading.enums as trading_enums
import octobot_trading.exchanges as exchanges


class Okex(exchanges.SpotCCXTExchange):
    MAX_PAGINATION_LIMIT: int = 100  # value from https://www.okex.com/docs/en/#spot-orders_pending
    DESCRIPTION = ""

    @classmethod
    def get_name(cls):
        return 'okex'

    @classmethod
    def is_supporting_exchange(cls, exchange_candidate_name) -> bool:
        return cls.get_name() == exchange_candidate_name

    async def get_open_orders(self, symbol=None, since=None, limit=None, **kwargs) -> list:
        return await super().get_open_orders(symbol=symbol,
                                             since=since,
                                             limit=self._fix_limit(limit),
                                             **kwargs)

    async def get_closed_orders(self, symbol=None, since=None, limit=None, **kwargs) -> list:
        return await super().get_closed_orders(symbol=symbol,
                                               since=since,
                                               limit=self._fix_limit(limit),
                                               **kwargs)

    async def _create_market_buy_order(self, symbol, quantity, price=None, params=None) -> dict:
        """
        Add price to default connector call for market orders https://github.com/ccxt/ccxt/issues/9523
        """
        return await self.connector.client.create_market_order(symbol=symbol, side='buy', amount=quantity,
                                                               price=price, params=params)

    async def _create_market_sell_order(self, symbol, quantity, price=None, params=None) -> dict:
        """
        Add price to default connector call for market orders https://github.com/ccxt/ccxt/issues/9523
        """
        return await self.connector.client.create_market_order(symbol=symbol, side='sell', amount=quantity,
                                                               price=price, params=params)

    def _fix_limit(self, limit: int) -> int:
        return min(self.MAX_PAGINATION_LIMIT, limit)

    def get_market_status(self, symbol, price_example=None, with_fixer=True):
        try:
            market_status = self._fix_market_status(copy.deepcopy(self.connector.client.market(symbol)))
            if with_fixer:
                market_status = exchanges.ExchangeMarketStatusFixer(market_status, price_example).market_status
            return market_status
        except ccxt.NotSupported:
            raise octobot_trading.errors.NotSupported
        except Exception as e:
            self.logger.error(f"Fail to get market status of {symbol}: {e}")
        return {}

    def _fix_market_status(self, market_status):
        market_status[trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION.value][
            trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION_AMOUNT.value] = self._get_digits_count(
            market_status[trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION.value][
                trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION_AMOUNT.value])
        market_status[trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION.value][
            trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION_PRICE.value] = self._get_digits_count(
            market_status[trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION.value][
                trading_enums.ExchangeConstantsMarketStatusColumns.PRECISION_PRICE.value])
        return market_status

    def _get_digits_count(self, value):
        return round(abs(math.log(value, 10)))
