python cvae_1.py \
    --batch 64 \
    -m 10 \
    --seed 1 \
    --log 3 \
    --dir "./data/Datasets/Drug response plam" \
    --layer 20 \
    --learn_rate 0.001 \
    --alpha 1 \
    --beta 1 \
    -L 1 \
    --save

python cvae_1.py \
    --batch 64 \
    -m 10 \
    --seed 1 \
    --log 3 \
    --dir "./data/Datasets/Drug response plam" \
    --layer 20 \
    --learn_rate 0.001 \
    --alpha 1 \
    --beta 1 \
    -L 1 \
    --rating \
    --load 1 \
    --save

    # --rating \
    # --gpu \
    # -N 20 \