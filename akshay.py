import math
import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras import layers
import math
import numpy as np
import pandas as pd
import wandb
import warnings
import tensorflow_addons as tfa
import matplotlib.pyplot as plt
import seaborn as sns
from tensorflow.keras.utils import plot_model


#ignore warnings
warnings.filterwarnings("ignore")


anony = "must"
print('https://wandb.ai/authorize')
CONFIG = dict(competition='TabTransformer', _wandb_kernel='tensorgirl')

train = pd.read_csv('DSWithGradeGroup.csv')

print(train.head())

all_features = [
    "priorbxresult",
    "clinstaget",
    "clinstagen",
    "clinstagem",
    "grade",
    "prepsa",
    "procname"
    ]

NUMERIC_FEATURE_NAMES = [
    "prepsa",
    "grade",
    ]

TARGET_FEATURE_NAME  = "procname"
TARGET_LABELS = ["ActiveSurveillance","BrachyTherapy",
"DVP",
"ExternalBeam",
"ProtonBeam",
"RP"
]
NUM_CLASSES = len(TARGET_LABELS)
CATEGORICAL_FEATURES_WITH_VOCABULARY = {
    "priorbxresult":sorted(list(train["priorbxresult"].unique())),
    "clinstaget": sorted(list(train["clinstaget"].unique())),
    "clinstagen": sorted(list(train["clinstagen"].unique())),
    "clinstagem": sorted(list(train["clinstagem"].unique())),}

CATEGORICAL_FEATURE_NAMES = list(CATEGORICAL_FEATURES_WITH_VOCABULARY.keys())
FEATURE_NAMES = NUMERIC_FEATURE_NAMES + CATEGORICAL_FEATURE_NAMES

df=train.describe()
print(df)

fig, ax = plt.subplots(3,3, figsize=(18, 18))
for i, feature in enumerate(NUMERIC_FEATURE_NAMES):
    sns.distplot(train[feature], color = "#ff355d", ax=ax[math.floor(i/3),i%3]).set_title(f'{feature} Distribution')
fig.savefig('output.svg')
pie, ax = plt.subplots(figsize=[18,8])
train.groupby('procname').size().plot(kind='pie',autopct='%.2f',ax=ax,title='Target distibution' , cmap = "Pastel1")
pie.savefig('output1.svg')

train, val = np.split(train.sample(frac=1), [int(0.8*len(train))])
train = train[all_features]
val = val[all_features]

train_data_file = "train_data.csv"
test_data_file = "test_data.csv"

train.to_csv(train_data_file, index=False, header=False)
val.to_csv(test_data_file, index=False, header=False)

train.to_csv("train_wandb.csv", index = False)
run = wandb.init(project='TabTransformer', name='training_data', anonymous=anony,config=CONFIG)
artifact = wandb.Artifact(name='training_data',type='dataset')
artifact.add_file("./train_wandb.csv")

wandb.log_artifact(artifact)
wandb.finish()

LEARNING_RATE = 0.001
WEIGHT_DECAY = 0.0001
DROPOUT_RATE = 0.1
BATCH_SIZE = 128
NUM_EPOCHS = 25
NUM_TRANSFORMER_BLOCKS = 3
NUM_HEADS = 4
EMBEDDING_DIMS = 16
MLP_HIDDEN_UNITS_FACTORS = [
    2,
    1,
]
NUM_MLP_BLOCKS = 2

def get_dataset_from_csv(csv_file_path, batch_size=128, shuffle=False):
    dataset = tf.data.experimental.make_csv_dataset(
        csv_file_path,
        batch_size=batch_size,
        column_names=all_features,
        label_name=TARGET_FEATURE_NAME,
        num_epochs=1,
        header=False,
        shuffle=shuffle,
    ).map(prepare_example, num_parallel_calls=tf.data.AUTOTUNE, deterministic=False)
    return dataset.cache()


target_label_lookup = layers.StringLookup(
    vocabulary=TARGET_LABELS, mask_token=None, num_oov_indices=0
)

def prepare_example(features, target):
    target_index = target_label_lookup(target)
    return features, target_index

def run_experiment(
    model,
    train_data_file,
    test_data_file,
    num_epochs,
    learning_rate,
    weight_decay,
    batch_size,
):

    optimizer = tfa.optimizers.AdamW(
        learning_rate=learning_rate, weight_decay=weight_decay
    )

    model.compile(
        optimizer=optimizer,
        loss=keras.losses.SparseCategoricalCrossentropy(),
        metrics=[keras.metrics.SparseCategoricalAccuracy()],
    )

    train_dataset = get_dataset_from_csv(train_data_file, batch_size, shuffle=True)
    validation_dataset = get_dataset_from_csv(test_data_file, batch_size)

    print("Start training the model...")
    history = model.fit(
        train_dataset, epochs=num_epochs, validation_data=validation_dataset
    )
    print("Model training finished")

    _, accuracy = model.evaluate(validation_dataset, verbose=0)

    print(f"Validation accuracy: {round(accuracy * 100, 2)}%")

    return history

def create_model_inputs():
    inputs = {}
    for feature_name in FEATURE_NAMES:
        if feature_name in NUMERIC_FEATURE_NAMES:
            inputs[feature_name] = layers.Input(
                name=feature_name, shape=(), dtype=tf.float32
            )
        else:
            inputs[feature_name] = layers.Input(
                name=feature_name, shape=(), dtype=tf.string
            )
    return inputs

def encode_inputs(inputs, embedding_dims):

    encoded_categorical_feature_list = []
    numerical_feature_list = []

    for feature_name in inputs:
        if feature_name in CATEGORICAL_FEATURE_NAMES:

            # Get the vocabulary of the categorical feature.
            vocabulary = CATEGORICAL_FEATURES_WITH_VOCABULARY[feature_name]

            # Create a lookup to convert string values to an integer indices.
            # Since we are not using a mask token nor expecting any out of vocabulary
            # (oov) token, we set mask_token to None and  num_oov_indices to 0.
            lookup = layers.StringLookup(
                vocabulary=vocabulary,
                mask_token=None,
                num_oov_indices=0,
                output_mode="int",
            )

            # Convert the string input values into integer indices.
            encoded_feature = lookup(inputs[feature_name])

            # Create an embedding layer with the specified dimensions.
            embedding = layers.Embedding(
                input_dim=len(vocabulary), output_dim=embedding_dims
            )

            # Convert the index values to embedding representations.
            encoded_categorical_feature = embedding(encoded_feature)
            encoded_categorical_feature_list.append(encoded_categorical_feature)

        else:

            # Use the numerical features as-is.
            numerical_feature = tf.expand_dims(inputs[feature_name], -1)
            numerical_feature_list.append(numerical_feature)

    return encoded_categorical_feature_list, numerical_feature_list

def create_mlp(hidden_units, dropout_rate, activation, normalization_layer, name=None):

    mlp_layers = []
    for units in hidden_units:
        mlp_layers.append(normalization_layer),
        mlp_layers.append(layers.Dense(units, activation=activation))
        mlp_layers.append(layers.Dropout(dropout_rate))

    return keras.Sequential(mlp_layers, name=name)

def create_tabtransformer_classifier(
    num_transformer_blocks,
    num_heads,
    embedding_dims,
    mlp_hidden_units_factors,
    dropout_rate,
    use_column_embedding=False,
):

    # Create model inputs.
    inputs = create_model_inputs()
    # encode features.
    encoded_categorical_feature_list, numerical_feature_list = encode_inputs(
        inputs, embedding_dims
    )
    # Stack categorical feature embeddings for the Tansformer.
    encoded_categorical_features = tf.stack(encoded_categorical_feature_list, axis=1)
    # Concatenate numerical features.
    numerical_features = layers.concatenate(numerical_feature_list)

    if use_column_embedding:
        num_columns = encoded_categorical_features.shape[1]
        column_embedding = layers.Embedding(
            input_dim=num_columns, output_dim=embedding_dims
        )
        column_indices = tf.range(start=0, limit=num_columns, delta=1)
        encoded_categorical_features = encoded_categorical_features + column_embedding(
            column_indices
        )
    for block_idx in range(num_transformer_blocks):
        # Create a multi-head attention layer.
        attention_output = layers.MultiHeadAttention(
            num_heads=num_heads,
            key_dim=embedding_dims,
            dropout=dropout_rate,
            name=f"multihead_attention_{block_idx}",
        )(encoded_categorical_features, encoded_categorical_features)
        # Skip connection 1.
        x = layers.Add(name=f"skip_connection1_{block_idx}")(
            [attention_output, encoded_categorical_features]
        )
        # Layer normalization 1.
        x = layers.LayerNormalization(name=f"layer_norm1_{block_idx}", epsilon=1e-6)(x)
        # Feedforward.
        feedforward_output = create_mlp(
            hidden_units=[embedding_dims],
            dropout_rate=dropout_rate,
            activation=keras.activations.gelu,
            normalization_layer=layers.LayerNormalization(epsilon=1e-6),
            name=f"feedforward_{block_idx}",
        )(x)
        # Skip connection 2.
        x = layers.Add(name=f"skip_connection2_{block_idx}")([feedforward_output, x])
        # Layer normalization 2.
        encoded_categorical_features = layers.LayerNormalization(
            name=f"layer_norm2_{block_idx}", epsilon=1e-6
        )(x)

        # Flatten the "contextualized" embeddings of the categorical features.
    categorical_features = layers.Flatten()(encoded_categorical_features)
    # Apply layer normalization to the numerical features.
    numerical_features = layers.LayerNormalization(epsilon=1e-6)(numerical_features)
    # Prepare the input for the final MLP block.
    features = layers.concatenate([categorical_features, numerical_features])

    # Compute MLP hidden_units.
    mlp_hidden_units = [
        factor * features.shape[-1] for factor in mlp_hidden_units_factors
    ]
    # Create final MLP.
    features = create_mlp(
        hidden_units=mlp_hidden_units,
        dropout_rate=dropout_rate,
        activation=keras.activations.selu,
        normalization_layer=layers.BatchNormalization(),
        name="MLP",
    )(features)


    outputs = layers.Dense(units=NUM_CLASSES, activation="softmax")(features)
    model = keras.Model(inputs=inputs, outputs=outputs)
    return model

tabtransformer_model = create_tabtransformer_classifier(
    num_transformer_blocks=NUM_TRANSFORMER_BLOCKS,
    num_heads=NUM_HEADS,
    embedding_dims=EMBEDDING_DIMS,
    mlp_hidden_units_factors=MLP_HIDDEN_UNITS_FACTORS,
    dropout_rate=DROPOUT_RATE,
)

print("Total model weights:", tabtransformer_model.count_params())


history = run_experiment(
    model=tabtransformer_model,
    train_data_file=train_data_file,
    test_data_file=test_data_file,
    num_epochs=NUM_EPOCHS,
    learning_rate=LEARNING_RATE,
    weight_decay=WEIGHT_DECAY,
    batch_size=BATCH_SIZE,
)

# def create_baseline_model(
#     embedding_dims, num_mlp_blocks, mlp_hidden_units_factors, dropout_rate
# ):
#
#     # Create model inputs.
#     inputs = create_model_inputs()
#     # encode features.
#     encoded_categorical_feature_list, numerical_feature_list = encode_inputs(
#         inputs, embedding_dims
#     )
#     # Concatenate all features.
#     features = layers.concatenate(
#         encoded_categorical_feature_list + numerical_feature_list
#     )
#     # Compute Feedforward layer units.
#     feedforward_units = [features.shape[-1]]
#
#     # Create several feedforwad layers with skip connections.
#     for layer_idx in range(num_mlp_blocks):
#         features = create_mlp(
#             hidden_units=feedforward_units,
#             dropout_rate=dropout_rate,
#             activation=keras.activations.gelu,
#             normalization_layer=layers.LayerNormalization(epsilon=1e-6),
#             name=f"feedforward_{layer_idx}",
#         )(features)
#         # Compute MLP hidden_units.
#         mlp_hidden_units = [
#             factor * features.shape[-1] for factor in mlp_hidden_units_factors
#         ]
#         # Create final MLP.
#         features = create_mlp(
#             hidden_units=mlp_hidden_units,
#             dropout_rate=dropout_rate,
#             activation=keras.activations.selu,
#             normalization_layer=layers.BatchNormalization(),
#             name="MLP",
#         )(features)
#
#         # Add a sigmoid as a binary classifer.
#         outputs = layers.Dense(units=NUM_CLASSES, activation="softmax")(features)
#         model1 = keras.Model(inputs=inputs, outputs=outputs)
#         return model1
#
# baseline_model = create_baseline_model(
#     embedding_dims=EMBEDDING_DIMS,
#     num_mlp_blocks=NUM_MLP_BLOCKS,
#     mlp_hidden_units_factors=MLP_HIDDEN_UNITS_FACTORS,
#     dropout_rate=DROPOUT_RATE,
# )
#
# print("Total model weights:", baseline_model.count_params())
#
# history = run_experiment(
#     model=baseline_model,
#     train_data_file=train_data_file,
#     test_data_file=test_data_file,
#     num_epochs=NUM_EPOCHS,
#     learning_rate=LEARNING_RATE,
#     weight_decay=WEIGHT_DECAY,
#     batch_size=BATCH_SIZE,
# )
#model = keras.models.load_model("best_model.h5")
sample = {
    "priorbxresult": "MOD",
    "clinstaget": "T1c",
    "clinstagen": "NX",
    "clinstagem": "MX",
    "grade": 1,
    "prepsa": 0.62,
}

input_dict = {name: tf.convert_to_tensor([value]) for name, value in sample.items()}
predictions = tabtransformer_model.predict(input_dict)
print(predictions)