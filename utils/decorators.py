from functools import wraps


def requires_character(func):
    """Декоратор: проверяет наличие персонажа перед выполнением команды."""
    @wraps(func)
    async def wrapper(self, ctx, *args, **kwargs):
        user = ctx.author.name.lower()
        if user not in self.players:
            await ctx.send(f'{ctx.author.name}, у тебя нет персонажа.')
            return
        return await func(self, ctx, *args, **kwargs)
    return wrapper
