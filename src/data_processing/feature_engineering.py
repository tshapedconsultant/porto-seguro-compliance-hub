"""
Feature Engineering Module - PROPERLY ARCHITECTED
Part of Insurance Claim Prediction - Responsible AI Architecture

Corrections applied:
1. Strict separation of Fit (Train) and Transform (Test) to prevent Data Leakage.
2. Null imputation preserves 'missingness' signal (critical for insurance).
3. Frequency Encoding added for high-cardinality categoricals.
4. Optimized Polars operations.
"""

import polars as pl
from typing import List, Dict, Optional, Tuple
import logging
from sklearn.model_selection import StratifiedKFold
import numpy as np

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ResponsibleFeatureEngineer:
    """
    Stateful feature engineer that prevents data leakage by saving
    statistics from the training set to apply to the test set.
    
    This is the CORRECT way to do feature engineering - learn statistics
    from training data only, then apply to test data.
    """
    
    def __init__(self, target_col: str = "target"):
        self.target_col = target_col
        self.medians: Dict[str, float] = {}
        self.category_counts: Dict[str, pl.DataFrame] = {}  # For frequency encoding
        self.trained = False
        self.cat_features: List[str] = []
        self.num_features: List[str] = []
        
    def fit(self, df: pl.DataFrame):
        """
        Learn statistics ONLY from the training data.
        
        This prevents data leakage - we never see test data statistics.
        
        Args:
            df: Training dataframe only
            
        Returns:
            self: For method chaining
        """
        logger.info("Fitting feature engineer on training data...")
        
        # Identify features
        feature_cols = [col for col in df.columns if col not in ["id", self.target_col]]
        self.cat_features = [col for col in feature_cols if "cat" in col.lower()]
        self.num_features = [col for col in feature_cols if col not in self.cat_features]
        
        logger.info(f"Found {len(self.cat_features)} categorical and {len(self.num_features)} numerical features")
        
        # 1. Learn Medians for Numerical (from TRAIN only)
        for col in self.num_features:
            self.medians[col] = float(df[col].median())
            
        # 2. Learn Frequencies for Categorical (Better than Mode)
        # Frequency encoding is more predictive than simple mode imputation
        for col in self.cat_features:
            # Save value counts to map later
            counts = df[col].value_counts()
            # Normalize to get frequency (0-1)
            total = counts["count"].sum()
            counts = counts.with_columns((pl.col("count") / total).alias(f"{col}_freq"))
            self.category_counts[col] = counts.select([col, f"{col}_freq"])
            
        self.trained = True
        logger.info("Fit complete. Statistics stored from training data only.")
        return self

    def transform(self, df: pl.DataFrame) -> pl.DataFrame:
        """
        Apply learned statistics to new data (Train or Test).
        
        This ensures no data leakage - test data uses training statistics.
        
        Args:
            df: Dataframe to transform (can be train or test)
            
        Returns:
            pl.DataFrame: Transformed dataframe with engineered features
        """
        if not self.trained:
            raise ValueError("Feature Engineer must be fit before transform!")
            
        logger.info(f"Transforming dataset shape: {df.shape}")
        df_eng = df.clone()
        
        # 1. Numerical: Create 'Is_Missing' flag AND Fill Nulls
        # (This preserves the signal that data was missing - critical for insurance)
        for col in self.num_features:
            if col not in df_eng.columns:
                continue
                
            # Always create missing flag (even if no nulls currently, for consistency)
            # This ensures the feature exists in both train and test
            df_eng = df_eng.with_columns(
                pl.col(col).is_null().cast(pl.Int8).alias(f"{col}_missing")
            )
            
            # Fill with learned median (from training data)
            median_val = self.medians.get(col, 0.0)
            df_eng = df_eng.with_columns(
                pl.col(col).fill_null(median_val)
            )

        # 2. Categorical: Frequency Encoding
        # This replaces the category ID with how common it is (very predictive)
        for col in self.cat_features:
            if col not in df_eng.columns:
                continue
                
            # Left join with learned frequencies
            # If a category in Test wasn't seen in Train, it gets null -> fill with 0
            if col in self.category_counts:
                freq_map = self.category_counts[col]
                df_eng = df_eng.join(freq_map, on=col, how="left")
                
                # Fill new unseen categories with 0 frequency
                df_eng = df_eng.with_columns(
                    pl.col(f"{col}_freq").fill_null(0.0)
                )
                
                # Also create missing flag for categorical
                if df_eng[col].null_count() > 0:
                    df_eng = df_eng.with_columns(
                        pl.col(col).is_null().cast(pl.Int8).alias(f"{col}_missing")
                    )

        # 3. Safe Interactions (Example - only if features exist)
        # Using polars expressions for speed
        if "ps_reg_01" in df_eng.columns and "ps_reg_02" in df_eng.columns:
            df_eng = df_eng.with_columns(
                (pl.col("ps_reg_01") * pl.col("ps_reg_02")).alias("interaction_reg1_reg2")
            )
        
        if len(self.num_features) >= 2:
            # Create interaction of first two numerical features if they exist
            feat1, feat2 = self.num_features[0], self.num_features[1]
            if feat1 in df_eng.columns and feat2 in df_eng.columns:
                df_eng = df_eng.with_columns(
                    (pl.col(feat1) + pl.col(feat2)).alias(f"{feat1}_plus_{feat2}")
                )

        logger.info(f"Transformation complete. Final shape: {df_eng.shape}")
        return df_eng


def get_stratified_split(
    df: pl.DataFrame, 
    target_col: str = "target", 
    test_size: float = 0.2,
    random_seed: int = 42
) -> Tuple[pl.DataFrame, pl.DataFrame]:
    """
    Create stratified train-test split using sklearn for proper class distribution.
    
    This is CRITICAL for imbalanced datasets (3.6% positive class).
    Random split can give unreliable metrics.
    
    Args:
        df: Full dataframe
        target_col: Target column name
        test_size: Proportion for test set
        random_seed: Random seed for reproducibility
        
    Returns:
        tuple: (train_df, test_df) as Polars DataFrames
    """
    logger.info(f"Creating stratified split: test_size={test_size}")
    
    # Use sklearn's stratified split for proper class distribution
    from sklearn.model_selection import train_test_split
    
    # Convert to numpy for sklearn
    y = df[target_col].to_numpy()
    indices = np.arange(len(df))
    
    # Stratified split ensures similar class distribution in train and test
    train_idx, test_idx = train_test_split(
        indices,
        test_size=test_size,
        stratify=y,  # CRITICAL: maintains class distribution
        random_state=random_seed
    )
    
    # Convert back to Polars
    train_df = df[train_idx]
    test_df = df[test_idx]
    
    # Verify class distribution
    train_dist = train_df[target_col].value_counts()
    test_dist = test_df[target_col].value_counts()
    
    logger.info(f"Train set: {len(train_df)} records")
    logger.info(f"Test set: {len(test_df)} records")
    logger.info(f"Train target distribution: {train_dist.to_dict()}")
    logger.info(f"Test target distribution: {test_dist.to_dict()}")
    
    return train_df, test_df


def get_stratified_kfold_splits(
    df: pl.DataFrame, 
    target_col: str = "target", 
    n_splits: int = 5,
    random_seed: int = 42
):
    """
    Generator for Stratified K-Fold splits compatible with Polars.
    Essential for cross-validation on imbalanced datasets.
    
    Args:
        df: Full dataframe
        target_col: Target column name
        n_splits: Number of folds
        random_seed: Random seed
        
    Yields:
        tuple: (fold_number, train_df, val_df) for each fold
    """
    logger.info(f"Creating {n_splits}-fold stratified splits")
    
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=random_seed)
    
    # Convert to numpy for sklearn
    y = df[target_col].to_numpy()
    indices = np.arange(len(df))
    
    for fold, (train_idx, val_idx) in enumerate(skf.split(indices, y)):
        train_df = df[train_idx]
        val_df = df[val_idx]
        yield fold, train_df, val_df


# Legacy function for backward compatibility (DEPRECATED - use ResponsibleFeatureEngineer)
def engineer_features(
    df: pl.DataFrame,
    target_col: str = "target"
) -> pl.DataFrame:
    """
    DEPRECATED: This function causes data leakage.
    
    Use ResponsibleFeatureEngineer class instead:
    
    fe = ResponsibleFeatureEngineer(target_col="target")
    fe.fit(train_df)
    train_eng = fe.transform(train_df)
    test_eng = fe.transform(test_df)
    """
    logger.warning("DEPRECATED: engineer_features() causes data leakage. Use ResponsibleFeatureEngineer class.")
    
    # For backward compatibility, create a temporary engineer
    fe = ResponsibleFeatureEngineer(target_col=target_col)
    fe.fit(df)  # Still has leakage if used incorrectly
    return fe.transform(df)


# Legacy function (DEPRECATED - use get_stratified_split)
def prepare_train_test_split(
    df: pl.DataFrame,
    target_col: str = "target",
    test_size: float = 0.2,
    random_seed: int = 42
) -> tuple:
    """
    DEPRECATED: This function uses random split which is risky for imbalanced data.
    
    Use get_stratified_split() instead for proper class distribution.
    """
    logger.warning("DEPRECATED: prepare_train_test_split() uses random split. Use get_stratified_split() for imbalanced data.")
    
    # Shuffle and split (NOT stratified - can cause issues)
    df_shuffled = df.sample(fraction=1.0, seed=random_seed)
    
    n_test = int(len(df_shuffled) * test_size)
    df_test = df_shuffled.head(n_test)
    df_train = df_shuffled.tail(len(df_shuffled) - n_test)
    
    # Separate features and target
    feature_cols = [col for col in df.columns if col not in ["id", target_col]]
    
    X_train = df_train.select(feature_cols)
    y_train = df_train.select([target_col])
    X_test = df_test.select(feature_cols)
    y_test = df_test.select([target_col])
    
    logger.info(f"Train set: {len(X_train)} records")
    logger.info(f"Test set: {len(X_test)} records")
    
    return X_train, X_test, y_train, y_test
