"""
Script to train hatespeech classifier
"""
import fire
import torch
import transformers
from transformers import (
    Trainer, TrainingArguments, AutoModelForSequenceClassification, AutoTokenizer
)
from hatedetection import BertForSequenceMultiClassification, load_datasets, extended_hate_categories
from hatedetection.metrics import compute_category_metrics


def load_model_and_tokenizer(model_name, max_length):
    """
    Load model and tokenizer
    """

    model = BertForSequenceMultiClassification.from_pretrained(
        model_name, return_dict=True, num_labels=len(extended_hate_categories)
    )

    model.train()

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    tokenizer.model_max_length = max_length

    return model, tokenizer

def tokenize(tokenizer, batch, context=True, padding='max_length', truncation=True):
    """
    Apply tokenization

    Arguments:
    ---------

    use_context: boolean (default True)
        Whether to add the context to the
    """

    if context:
        args = [batch['context'], batch['text']]
    else:
        args = [batch['text']]

    return tokenizer(*args, padding='max_length', truncation=True)



def train_category_classifier(
    output_path, train_path=None, test_path=None, use_context=False,
    model_name = 'dccuchile/bert-base-spanish-wwm-cased', batch_size=32, eval_batch_size=16,
    max_length=None, epochs=5, warmup_proportion=0.1,
    ):

    """
    Train and save hatespeech classifier

    Arguments:
    ----------

    train_path:
        Path to training data
    test_path:
        Path to test data
    """
    print("*"*80)
    print("Training hate speech category classifier")
    print(f"Uses context: {use_context}")
    if not max_length:
        max_length = 256 if use_context else 128
    print(f"Tokenizer max length: {max_length}")
    print("*"*80, end="\n"*3)

    print("Loading datasets... ", end="")
    train_dataset, dev_dataset, test_dataset = load_datasets(train_path, test_path)

    train_dataset = train_dataset.filter(lambda x: x["HATEFUL"] > 0)
    dev_dataset = dev_dataset.filter(lambda x: x["HATEFUL"] > 0)
    test_dataset = test_dataset.filter(lambda x: x["HATEFUL"] > 0)
    print("Done")

    device = "cuda" if torch.cuda.is_available() else "cpu"


    print("")
    print("Loading model and tokenizer... ", end="")
    model, tokenizer = load_model_and_tokenizer(model_name, max_length)
    print("Done")


    my_tokenize = lambda batch: tokenize(tokenizer, batch, context=use_context)

    print("Tokenizing and formatting datasets...")
    train_dataset = train_dataset.map(my_tokenize, batched=True, batch_size=batch_size)
    dev_dataset = dev_dataset.map(my_tokenize, batched=True, batch_size=eval_batch_size)
    test_dataset = test_dataset.map(my_tokenize, batched=True, batch_size=eval_batch_size)


    def format_dataset(dataset):
        def get_category_labels(examples):
            return {'labels': torch.Tensor([examples[cat] for cat in extended_hate_categories])}
        dataset = dataset.map(get_category_labels)
        dataset.set_format(type='torch', columns=['input_ids', 'token_type_ids', 'attention_mask', 'labels'])
        return dataset

    train_dataset = format_dataset(train_dataset)
    dev_dataset = format_dataset(dev_dataset)
    test_dataset = format_dataset(test_dataset)

    """
    Finally, train!
    """

    print("\n"*3, "Training...")

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
        metric_for_best_model="mean_f1",
    )

    results = []

    trainer = Trainer(
        model=model,
        args=training_args,
        compute_metrics=compute_category_metrics,
        train_dataset=train_dataset,
        eval_dataset=dev_dataset,
    )

    trainer.train()
    """
    Evaluate
    """
    trainer.evaluate(dev_dataset)

    print("\n"*3, "Saving...")

    trainer.save_model(output_path)
    tokenizer.save_pretrained(output_path)

    print(f"Models saved at {output_path}")

if __name__ == '__main__':
    fire.Fire(train_category_classifier)
