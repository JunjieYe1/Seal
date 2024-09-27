def normalize(x, lower_bound=900, upper_bound=3570, middle_point=2000):
    if x <= lower_bound:
        return 0
    elif x >= upper_bound:
        return 1
    elif x <= middle_point:
        return (x - lower_bound) / (middle_point - lower_bound) * 0.5
    else:
        return 0.5 + (x - middle_point) / (upper_bound - middle_point) * 0.5


max_value_x = 3570  # 假设 position_x 的最大值为 4000
max_value_y = 3833  # 假设 position_y 的最大值为 4000
middle_point_x = 2200
middle_point_y = 1900
min_x = 900
min_y = 390


position_x = 1880
position_y = 2560
normalized_x = normalize(position_x, min_x, max_value_x)
normalized_y = normalize(position_y, min_y, max_value_y, middle_point_y)

print(normalized_x,normalized_y)
