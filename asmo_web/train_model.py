import pandas as pd
from catboost import CatBoostRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error
import numpy as np


df = pd.read_csv("../moex_options_with_underlying.csv")

# удаляем NaN
df = df.dropna()

target = "NEXT_RET_1D"

features = [
    "UNDERLYING_PRICE",
    "UNDERLYING_RET_1D",
    "HV_20",
    "STRIKE",
    "TTM_DAYS",
    "MONEYNESS",
    "LOG_MONEYNESS",
    "INTRINSIC",
    "SETTLEPRICE",
    "VOLUME",
    "NUMTRADES",
    "OPENPOSITION"
]

X = df[features]
y = df[target]


X_train, X_test, y_train, y_test = train_test_split(
    X, y,
    test_size=0.2,
    random_state=42
)


model = CatBoostRegressor(
    iterations=700,
    depth=6,
    learning_rate=0.03,
    loss_function="RMSE",
    verbose=100
)

model.fit(X_train, y_train)


pred = model.predict(X_test)

rmse = np.sqrt(mean_squared_error(y_test, pred))

print("RMSE:", rmse)

model.save_model("catboost_options_model.cbm")

print("Модель сохранена")