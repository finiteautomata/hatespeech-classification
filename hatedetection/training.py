from .metrics import compute_hate_metrics
from .preprocessing import special_tokens
from transformers import (
    BertTokenizerFast, TrainingArguments, Trainer,
    AutoModelForSequenceClassification, AutoTokenizer
)

def load_hatespeech_model_and_tokenizer(model_name, context, max_length=None):
    """
    Load model and tokenizer for hate speech classification
    """

    lengths = {
        'none': 128,
        'title': 256,
        'body': 512
    }
    if not max_length:
        max_length = lengths[context]

    id2label = {0: 'Not hateful', 1: 'Hateful'}
    label2id = {v:k for k,v in id2label.items()}

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name, return_dict=True, num_labels=2
    )

    model.config.id2label = id2label
    model.config.label2id = label2id

    model.train()

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.model_max_length = max_length

    """
    Check for new tokens
    """

    vocab = tokenizer.get_vocab()
    new_tokens_to_add = [tok for tok in special_tokens if tok not in tokenizer.get_vocab()]

    if new_tokens_to_add:
        """
        TODO: Perdoname Wilkinson, te he fallado

        Hay una interfaz diferente acá, no entiendo bien por qué
        """
        if type(tokenizer) is BertTokenizerFast:
            tokenizer.add_special_tokens({'additional_special_tokens': new_tokens_to_add})
        else:
            tokenizer.add_special_tokens(new_tokens_to_add)
        model.resize_token_embeddings(len(tokenizer))
    return model, tokenizer


def tokenize(tokenizer, batch, context, padding='max_length', truncation='longest_first'):
    """
    Apply tokenization

    Arguments:
    ---------

    context: string (default True)
        Type of allowed context. Options are ['none', 'title', 'body']
    """

    if context == 'title':
        args = [batch['title'], batch['text']]
    elif context == 'body':
        args = [batch['body'], batch['text']]
    else:
        args = [batch['text']]

    return tokenizer(*args, padding='max_length', truncation=True)


def train_hatespeech_classifier(
    model, tokenize_fun, train_dataset, dev_dataset,
    batch_size, eval_batch_size, max_length=None, epochs=10, warmup_proportion=0.1,
    ):
    """
    Train hate speech classifier
    """


    print("Tokenizing and formatting datasets...")

    train_dataset = train_dataset.map(tokenize_fun, batched=True, batch_size=batch_size)
    dev_dataset = dev_dataset.map(tokenize_fun, batched=True, batch_size=eval_batch_size)


    def format_dataset(dataset):
        dataset = dataset.map(lambda examples: {'labels': examples['HATEFUL']})
        dataset.set_format(type='torch', columns=['input_ids', 'token_type_ids', 'attention_mask', 'labels'])
        return dataset

    train_dataset = format_dataset(train_dataset)
    dev_dataset = format_dataset(dev_dataset)

    """
    Finally, train!
    """

    total_steps = (epochs * len(train_dataset)) // batch_size
    warmup_steps = int(warmup_proportion * total_steps)
    training_args = TrainingArguments(
        output_dir='./results',
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=eval_batch_size,
        warmup_steps=warmup_steps,
        evaluation_strategy="epoch",
        do_eval=False,
        weight_decay=0.01,
        logging_dir='./logs',
        load_best_model_at_end=True,
        metric_for_best_model="f1",
    )

    results = []

    trainer = Trainer(
        model=model,
        args=training_args,
        compute_metrics=compute_hate_metrics,
        train_dataset=train_dataset,
        eval_dataset=dev_dataset,
    )

    trainer.train()

    evaluation =  trainer.evaluate(dev_dataset)
    return trainer, evaluation