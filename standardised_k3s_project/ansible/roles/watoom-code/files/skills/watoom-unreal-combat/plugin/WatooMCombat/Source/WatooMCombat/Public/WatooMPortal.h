#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Engine/HitResult.h"
#include "WatooMPortal.generated.h"

class UBoxComponent;
class UNiagaraComponent;
class UNiagaraSystem;

/**
 * A walk-in portal: a pawn that enters the box is teleported to Destination (facing DestinationYaw). Server-authoritative:
 * only the server moves the pawn; the movement replicates. A pawn just teleported is ignored by every portal for
 * CooldownSeconds, so a portal whose destination sits on another portal does not bounce it back.
 * Place with level.place_actor, set BoxExtent / Destination / DestinationYaw (unreal_dungeon.py does it for dungeon
 * entrances and exits). Fx is an optional looping Niagara system shown at the portal (e.g. a generated aura).
 * Why (T-0015, 2026-11-19): the dungeon under the mountain-top arch sits below the landscape, and a hole would need the
 * landscape material to route a visibility mask; a portal reaches it without touching the terrain, matching the game's
 * portal design (T-0025).
 */
UCLASS()
class WATOOMCOMBAT_API AWatooMPortal : public AActor
{
	GENERATED_BODY()
public:
	AWatooMPortal();

	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Portal") FVector BoxExtent = FVector(150.f, 150.f, 200.f);
	/** World location the pawn's capsule centre is moved to. */
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Portal") FVector Destination = FVector::ZeroVector;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Portal") float DestinationYaw = 0.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Portal") float CooldownSeconds = 2.f;
	UPROPERTY(EditAnywhere, BlueprintReadOnly, Category = "Portal") TObjectPtr<UNiagaraSystem> Fx;

	/** Server: move a pawn to Destination now (also what the overlap does). False if it is on cooldown or the move failed. */
	UFUNCTION(BlueprintCallable, BlueprintAuthorityOnly, Category = "Portal") bool Send(APawn* Pawn);

	virtual void OnConstruction(const FTransform& Transform) override;

protected:
	virtual void BeginPlay() override;
	UFUNCTION() void OnOverlap(UPrimitiveComponent* Comp, AActor* Other, UPrimitiveComponent* OtherComp, int32 BodyIndex, bool bFromSweep, const FHitResult& Sweep);

	UPROPERTY(VisibleAnywhere, Category = "Portal") TObjectPtr<UBoxComponent> Box;
	UPROPERTY(VisibleAnywhere, Category = "Portal") TObjectPtr<UNiagaraComponent> FxComponent;
};
