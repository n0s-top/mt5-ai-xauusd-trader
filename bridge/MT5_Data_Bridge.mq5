//+------------------------------------------------------------------+
//| MT5 Data Bridge - Read Only                                      |
//| Export M1 OHLCV data for Python scalping                          |
//+------------------------------------------------------------------+
#property strict
#property version "1.00"

input string InpSymbol = "XAUUSDc";
input int InpBars = 5000;
input int InpUpdateSeconds = 5;

int OnInit()
{
   if(!SymbolSelect(InpSymbol, true))
   {
      Print("Cannot select symbol: ", InpSymbol);
      return INIT_FAILED;
   }

   if(!EventSetTimer(MathMax(1, InpUpdateSeconds)))
      return INIT_FAILED;

   Print("MT5 Data Bridge started: ", InpSymbol);
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason)
{
   EventKillTimer();
}

void OnTimer()
{
   MqlTick tick;
   if(SymbolInfoTick(InpSymbol, tick))
   {
      int quote = FileOpen("MT5_" + InpSymbol + "_quote.csv",
                           FILE_WRITE | FILE_CSV | FILE_COMMON, ',');
      if(quote != INVALID_HANDLE)
      {
         FileWrite(quote, "symbol", "time", "bid", "ask", "tick_size", "tick_value",
                   "volume_min", "volume_max", "volume_step");
         FileWrite(quote, InpSymbol, (long)tick.time, tick.bid, tick.ask,
                   SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_SIZE),
                   SymbolInfoDouble(InpSymbol, SYMBOL_TRADE_TICK_VALUE_LOSS),
                   SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MIN),
                   SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_MAX),
                   SymbolInfoDouble(InpSymbol, SYMBOL_VOLUME_STEP));
         FileClose(quote);
      }
   }
   MqlRates rates[];

   // Start at shift 1: exclude the currently forming M1 candle.
   int copied = CopyRates(
      InpSymbol,
      PERIOD_M1,
      1,
      InpBars,
      rates
   );

   if(copied <= 0)
   {
      Print("CopyRates failed: ", GetLastError());
      return;
   }

   string filename = "MT5_" + InpSymbol + "_M1.csv";

   int handle = FileOpen(
      filename,
      FILE_WRITE | FILE_CSV | FILE_COMMON,
      ','
   );

   if(handle == INVALID_HANDLE)
   {
      Print("FileOpen failed: ", GetLastError());
      return;
   }

   FileWrite(
      handle,
      "time",
      "open",
      "high",
      "low",
      "close",
      "tick_volume"
   );

   for(int i = 0; i < copied; i++)
   {
      FileWrite(
         handle,
         (long)rates[i].time,
         DoubleToString(rates[i].open, _Digits),
         DoubleToString(rates[i].high, _Digits),
         DoubleToString(rates[i].low, _Digits),
         DoubleToString(rates[i].close, _Digits),
         (long)rates[i].tick_volume
      );
   }

   FileClose(handle);

   Print("Exported ", copied, " M1 bars");
}
