                f"Còn khoảng **{remaining} phút**."
            )
        await interaction.followup.send(message, ephemeral=True)
    except Exception as error:
        await _error(interaction, "event", error)


def _choices():
    return [
        app_commands.Choice(name=JOBS[key][0], value=key)
        for key in JOBS
    ]


def _technology_choices():
    return [
        app_commands.Choice(name=value[0], value=key)
        for key, value in TECHNOLOGIES.items()
    ]


async def setup(bot):
    # commands.kingdom must be loaded first because it owns the /kingdom group.
    await asyncio.to_thread(ensure_schema)
    group = bot.tree.get_command("kingdom")
    if group is None:
        raise RuntimeError(
            "Không tìm thấy /kingdom. Hãy load commands.kingdom trước "
            "commands.kingdom_management."
        )

    # app_commands.Command() không nhận tham số choices.
    # Gắn choices trực tiếp vào callback bằng app_commands.choices().
    assign_callback = app_commands.choices(
        profession=_choices()
    )(assign)

    unassign_callback = app_commands.choices(
        profession=_choices()
    )(unassign)

    research_callback = app_commands.choices(
        technology=_technology_choices()
    )(research)

    commands_to_add = [
        app_commands.Command(
            name="population",
            description="Xem dân số và dân sinh",
            callback=population
        ),
        app_commands.Command(
            name="workers",
            description="Xem công nhân và chuyên môn",
            callback=workers
        ),
        app_commands.Command(
            name="assign",
            description="Phân công dân vào nghề",
            callback=assign_callback
        ),
        app_commands.Command(
            name="unassign",
            description="Thu hồi công nhân khỏi nghề",
            callback=unassign_callback
        ),
        app_commands.Command(
            name="farming",
            description="Thu hoạch sản lượng ngoại tuyến",
            callback=farming
        ),
        app_commands.Command(
            name="production",
            description="Xem tốc độ sản xuất",
            callback=production
        ),
        app_commands.Command(
            name="resources",
            description="Xem kho tài nguyên",
            callback=resources
        ),
        app_commands.Command(
            name="buildings",
            description="Xem công trình Kingdom",
            callback=buildings
        ),
        app_commands.Command(
            name="technology",
            description="Xem cây công nghệ",
            callback=technology
        ),
        app_commands.Command(
            name="research",
            description="Nghiên cứu công nghệ",
            callback=research_callback
        ),
        app_commands.Command(
            name="event",
            description="Xem sự kiện Kingdom",
            callback=event
        ),
    ]

    for command in commands_to_add:
        if group.get_command(command.name) is None:
            group.add_command(command)

    print("Loaded: kingdom management", flush=True)

