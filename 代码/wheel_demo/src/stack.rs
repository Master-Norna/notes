//! 最小 Stack 实现：条目是 VecStore 里的索引，槽内按 push 序存放，
//! peek_earliest 取 deadline 最早的条目（上层轮级联时需要）。
use std::borrow::Borrow;
use std::hash::Hash;

/// 测试用条目：deadline（ms）+ 标签
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Item(pub u64, pub &'static str);

#[derive(Debug, Default)]
pub struct VecStore {
    pub items: Vec<Item>,
}

pub trait ItemStack {
    type Item: Eq;
    fn get(&self, idx: usize) -> &Self::Item;
}

impl ItemStack for VecStore {
    type Item = Item;
    fn get(&self, idx: usize) -> &Self::Item {
        &self.items[idx]
    }
}

pub trait Stack: Default {
    type Owned: Borrow<Self::Borrowed>;
    type Borrowed: Eq + Hash;
    type Store;

    fn is_empty(&self) -> bool;
    fn push(&mut self, item: Self::Owned, store: &mut Self::Store);
    fn pop(&mut self, store: &mut Self::Store) -> Option<Self::Owned>;
    fn peek(&self) -> Option<Self::Owned>;
    fn peek_earliest(&self, store: &Self::Store) -> Option<Self::Owned>;
    fn remove(&mut self, item: &Self::Borrowed, store: &mut Self::Store);
    fn when(item: &Self::Borrowed, store: &mut Self::Store) -> u64;
}

pub type Key = usize;

/// 每个槽一个 Vec 栈（按 64 槽分桶）
#[derive(Debug)]
pub struct SlotStack {
    pub slots: [Vec<Key>; 64],
}

impl Default for SlotStack {
    fn default() -> Self {
        SlotStack { slots: std::array::from_fn(|_| Vec::new()) }
    }
}

impl Stack for SlotStack {
    type Owned = Key;
    type Borrowed = Key;
    type Store = VecStore;

    fn is_empty(&self) -> bool {
        self.slots.iter().all(|s| s.is_empty())
    }

    fn push(&mut self, item: Self::Owned, _store: &mut Self::Store) {
        self.slots[item].push(item);
    }

    fn pop(&mut self, _store: &mut Self::Store) -> Option<Self::Owned> {
        self.slots.iter_mut().find_map(|s| s.pop())
    }

    fn peek(&self) -> Option<Self::Owned> {
        self.slots.iter().find_map(|s| s.last().copied())
    }

    fn peek_earliest(&self, store: &Self::Store) -> Option<Self::Owned> {
        self.slots
            .iter()
            .filter(|s| !s.is_empty())
            .filter_map(|s| s.last().copied())
            .min_by_key(|k| store.get(*k).0)
    }

    fn remove(&mut self, item: &Self::Borrowed, _store: &mut Self::Store) {
        if let Some(s) = self.slots.get_mut(*item) {
            s.retain(|k| k != item);
        }
    }

    fn when(item: &Self::Borrowed, store: &mut Self::Store) -> u64 {
        store.get(*item).0
    }
}
